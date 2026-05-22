from __future__ import annotations

import json
from contextlib import nullcontext

from .db import Database
from .embeddings import HashingEmbedder, cosine
from .models import ClaimCandidate, MemoryLevel, MemoryType, WriteDecision, WriteDecisionResult
from .policy import MemoryPolicy
from .scoring import save_score
from .utils import json_dumps, new_id, normalize_key, now_iso


class MemoryWriteGovernor:
    def __init__(self, db: Database, policy: MemoryPolicy | None = None):
        self.db = db
        self.embedder = HashingEmbedder()
        self.policy = policy or MemoryPolicy.default()

    def decide(self, candidate: ClaimCandidate, *, project_id: str = "default", con=None) -> WriteDecisionResult:
        reasons: list[str] = []

        if candidate.evidence_id and candidate.memory_level == MemoryLevel.evidence_memory:
            reasons.append("raw evidence should be preserved immutably")
            return WriteDecisionResult(
                decision=WriteDecision.save_new,
                memory_level=MemoryLevel.evidence_memory,
                save_score=1.0,
                reasons=reasons,
            )

        if candidate.privacy_sensitivity >= self.policy.human_review_privacy_threshold and candidate.user_explicitness < self.policy.explicit_override_threshold:
            reasons.append("high privacy sensitivity without explicit save instruction")
            return WriteDecisionResult(
                decision=WriteDecision.needs_human_review,
                memory_level=MemoryLevel.session_memory,
                save_score=0.2,
                reasons=reasons,
                requires_review=True,
            )

        similar = self.find_similar_claim(candidate, project_id=project_id, con=con)
        if similar and similar["score"] >= self.policy.near_duplicate_threshold:
            if _looks_contradictory(candidate, similar):
                reasons.append("near-duplicate wording but conflicting polarity/object; save for contradiction scan")
            elif candidate.memory_type == MemoryType.correction:
                reasons.append("correction updates an existing related claim")
                return WriteDecisionResult(
                    decision=WriteDecision.update_existing,
                    memory_level=MemoryLevel.project_memory,
                    save_score=0.82,
                    reasons=reasons,
                    matched_claim_id=similar["id"],
                )
            else:
                reasons.append("near-duplicate existing claim")
                return WriteDecisionResult(
                    decision=WriteDecision.merge_with_existing,
                    memory_level=MemoryLevel.project_memory,
                    save_score=0.75,
                    reasons=reasons,
                    matched_claim_id=similar["id"],
                )

        if candidate.memory_type == MemoryType.inference and candidate.source_quality < self.policy.inference_review_source_quality:
            reasons.append("low-source-quality inference")
            return WriteDecisionResult(
                decision=WriteDecision.save_as_inference_only,
                memory_level=MemoryLevel.project_memory,
                save_score=0.45,
                reasons=reasons,
                requires_review=True,
            )

        score = save_score(candidate)
        if candidate.user_explicitness >= self.policy.explicit_override_threshold:
            reasons.append("explicit user instruction or correction")
        if candidate.project_relevance >= 0.75:
            reasons.append("durable project relevance")
        if candidate.source_quality >= 0.75:
            reasons.append("strong source quality")
        if candidate.contradiction_value >= 0.7:
            reasons.append("potential contradiction should be tracked")

        if score >= self.policy.durable_save_threshold:
            decision = WriteDecision.save_new
            level = MemoryLevel.project_memory
        elif score >= self.policy.session_save_threshold:
            decision = WriteDecision.session_only
            level = MemoryLevel.session_memory
            reasons.append("moderate score; keep out of durable memory")
        else:
            decision = WriteDecision.reject
            level = MemoryLevel.do_not_save
            reasons.append("low save score")

        return WriteDecisionResult(decision=decision, memory_level=level, save_score=score, reasons=reasons)

    def commit_candidate(
        self,
        candidate: ClaimCandidate,
        project_id: str = "default",
        *,
        con=None,
        autocommit: bool = True,
    ) -> WriteDecisionResult:
        result = self.decide(candidate, project_id=project_id, con=con)
        self.audit(candidate, result, con=con, autocommit=autocommit)

        if result.decision == WriteDecision.merge_with_existing and result.matched_claim_id:
            self._merge_claim(result.matched_claim_id, candidate, con=con, autocommit=autocommit)
            return result

        if result.decision == WriteDecision.update_existing and result.matched_claim_id:
            self._supersede_claim(result.matched_claim_id, candidate, con=con, autocommit=autocommit)
            # Save the correction as an active claim too, so the system can trace the replacement.
            result = WriteDecisionResult(
                decision=WriteDecision.save_new,
                memory_level=MemoryLevel.project_memory,
                save_score=result.save_score,
                reasons=result.reasons + ["saved replacement claim after superseding old claim"],
            )

        if result.decision not in {
            WriteDecision.save_new,
            WriteDecision.save_as_inference_only,
            WriteDecision.needs_human_review,
        }:
            return result

        status = "pending_review" if result.requires_review else "active"
        now = now_iso()
        claim_id = new_id("claim")
        con_ctx = nullcontext(con) if con is not None else self.db.connect()
        with con_ctx as active_con:
            active_con.execute(
                """
                INSERT INTO memory_claims
                (id, project_id, subject, predicate, object, claim_text, memory_type, memory_level, status,
                 confidence, salience, source_quality, valid_from, valid_to, created_at, updated_at, last_touched, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    claim_id,
                    project_id,
                    candidate.subject,
                    candidate.predicate,
                    candidate.object,
                    candidate.claim_text,
                    candidate.memory_type.value,
                    result.memory_level.value,
                    status,
                    candidate.confidence,
                    candidate.salience,
                    candidate.source_quality,
                    candidate.valid_from,
                    candidate.valid_to,
                    now,
                    now,
                    now,
                    json_dumps(candidate.metadata),
                ),
            )
            active_con.execute(
                "INSERT INTO memory_claims_fts (claim_id, subject, predicate, object, claim_text) VALUES (?, ?, ?, ?, ?)",
                (claim_id, candidate.subject, candidate.predicate, candidate.object, candidate.claim_text),
            )
            vector = self.embedder.embed(candidate.claim_text)
            active_con.execute(
                "INSERT INTO embeddings (id, owner_type, owner_id, vector_json, model, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (new_id("emb"), "claim", claim_id, json.dumps(vector), "hashing-embedding-v1", now),
            )
            if candidate.evidence_id:
                active_con.execute(
                    """
                    INSERT INTO claim_evidence_links
                    (id, claim_id, evidence_id, chunk_id, span_id, support_type, confidence, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        new_id("link"),
                        claim_id,
                        candidate.evidence_id,
                        candidate.chunk_id,
                        candidate.span_id,
                        "supports",
                        candidate.confidence,
                        now,
                    ),
                )
            if autocommit:
                active_con.commit()
        result.matched_claim_id = claim_id
        return result

    def find_similar_claim(self, candidate: ClaimCandidate, *, project_id: str = "default", con=None) -> dict | None:
        query_vec = self.embedder.embed(candidate.claim_text)
        con_ctx = nullcontext(con) if con is not None else self.db.connect()
        with con_ctx as active_con:
            rows = active_con.execute(
                """
                SELECT c.id, c.claim_text, c.subject, c.predicate, c.object, e.vector_json
                FROM memory_claims c
                JOIN embeddings e ON e.owner_type = 'claim' AND e.owner_id = c.id
                WHERE c.project_id = ? AND c.status IN ('active', 'pending_review', 'disputed')
                LIMIT 500
                """,
                (project_id,),
            ).fetchall()
        best = None
        for row in rows:
            vec = json.loads(row["vector_json"])
            sem = cosine(query_vec, vec)
            same_key = (
                normalize_key(candidate.subject) == normalize_key(row["subject"])
                and normalize_key(candidate.predicate) == normalize_key(row["predicate"])
            )
            score = sem + (0.15 if same_key else 0.0)
            if best is None or score > best["score"]:
                best = {
                    "id": row["id"],
                    "claim_text": row["claim_text"],
                    "subject": row["subject"],
                    "predicate": row["predicate"],
                    "object": row["object"],
                    "score": score,
                }
        return best

    def _merge_claim(self, claim_id: str, candidate: ClaimCandidate, *, con=None, autocommit: bool = True) -> None:
        now = now_iso()
        con_ctx = nullcontext(con) if con is not None else self.db.connect()
        with con_ctx as active_con:
            active_con.execute(
                """
                UPDATE memory_claims
                SET salience = MIN(1.0, salience + 0.08),
                    confidence = MIN(1.0, confidence + 0.04),
                    updated_at = ?,
                    last_touched = ?
                WHERE id = ?
                """,
                (now, now, claim_id),
            )
            if candidate.evidence_id:
                active_con.execute(
                    """
                    INSERT INTO claim_evidence_links
                    (id, claim_id, evidence_id, chunk_id, span_id, support_type, confidence, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        new_id("link"),
                        claim_id,
                        candidate.evidence_id,
                        candidate.chunk_id,
                        candidate.span_id,
                        "corroborates",
                        candidate.confidence,
                        now,
                    ),
                )
            if autocommit:
                active_con.commit()

    def _supersede_claim(self, claim_id: str, candidate: ClaimCandidate, *, con=None, autocommit: bool = True) -> None:
        now = now_iso()
        con_ctx = nullcontext(con) if con is not None else self.db.connect()
        with con_ctx as active_con:
            before = active_con.execute("SELECT * FROM memory_claims WHERE id = ?", (claim_id,)).fetchone()
            active_con.execute(
                "UPDATE memory_claims SET status = 'superseded', updated_at = ?, last_touched = ? WHERE id = ?",
                (now, now, claim_id),
            )
            active_con.execute(
                """
                INSERT INTO lifecycle_events
                (id, claim_id, event_type, before_json, after_json, reason, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id("life"),
                    claim_id,
                    "superseded",
                    json_dumps(dict(before) if before else {}),
                    candidate.model_dump_json(),
                    "correction candidate superseded related claim",
                    now,
                ),
            )
            if autocommit:
                active_con.commit()

    def audit(self, candidate: ClaimCandidate, result: WriteDecisionResult, *, con=None, autocommit: bool = True) -> None:
        con_ctx = nullcontext(con) if con is not None else self.db.connect()
        with con_ctx as active_con:
            active_con.execute(
                "INSERT INTO memory_write_audit (id, candidate_json, decision, reason_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    new_id("audit"),
                    candidate.model_dump_json(),
                    result.decision.value,
                    json_dumps(result.reasons),
                    now_iso(),
                ),
            )
            if autocommit:
                active_con.commit()


def _has_negation(text: str) -> bool:
    words = {w.strip(".,;:!?()[]{}\"'").lower() for w in text.split()}
    return bool(words & {"not", "no", "never", "cannot", "can't", "isn't", "wasn't", "won't", "without", "instead"})


def _looks_contradictory(candidate: ClaimCandidate, similar: dict) -> bool:
    same_key = (
        normalize_key(candidate.subject) == normalize_key(similar.get("subject", ""))
        and normalize_key(candidate.predicate) == normalize_key(similar.get("predicate", ""))
    )
    if not same_key:
        return False
    different_object = normalize_key(candidate.object) != normalize_key(similar.get("object", ""))
    different_negation = _has_negation(candidate.claim_text) != _has_negation(similar.get("claim_text", ""))
    return different_object and (different_negation or candidate.memory_type == MemoryType.correction)
