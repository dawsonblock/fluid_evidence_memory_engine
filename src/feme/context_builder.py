from __future__ import annotations

from .db import Database
from .models import ContextPacket
from .provenance import ProvenanceGraph
from .retrieval import RetrievalPlanner
from .utils import json_dumps, new_id, now_iso


class ContextBuilder:
    def __init__(self, db: Database):
        self.db = db
        self.retrieval = RetrievalPlanner(db)

    def build(self, question: str, *, project_id: str = "default", token_budget: int = 12000) -> ContextPacket:
        results = self.retrieval.search(question, project_id=project_id, top_k=24)
        included: list[dict] = []
        excluded: list[dict] = []
        warnings: list[str] = []
        used_tokens = 0
        for result in results:
            estimate = max(1, len(result.text.split()))
            if used_tokens + estimate > token_budget:
                excluded.append({"id": result.id, "kind": result.kind, "reason": "token_budget_exceeded", "estimated_tokens": estimate})
                continue
            item = result.model_dump()
            item["estimated_tokens"] = estimate
            if result.kind == "claim" and result.claim_id:
                item["supporting_evidence"] = self._supporting_evidence(result.claim_id)
                item["contradictions"] = self._contradictions(result.claim_id)
                status = item["metadata"].get("status")
                if status == "disputed":
                    warnings.append(f"Claim {result.claim_id} is disputed; inspect contradiction records before relying on it.")
                if not item["supporting_evidence"]:
                    warnings.append(f"Claim {result.claim_id} has no source span link; treat as lower-trust memory.")
                try:
                    item["provenance_trace"] = ProvenanceGraph(self.db).trace_claim(result.claim_id)
                except Exception:
                    item["provenance_trace"] = None
            if result.kind == "chunk" and result.evidence_id:
                item["source"] = self._evidence_source(result.evidence_id)
            included.append(item)
            used_tokens += estimate
        risk_summary = self._risk_summary(included)
        packet = ContextPacket(
            question=question,
            token_budget=token_budget,
            included=included,
            excluded=excluded,
            warnings=warnings,
            metadata={"used_estimated_tokens": used_tokens, "project_id": project_id, "builder": "context-builder-v3", "risk_summary": risk_summary},
        )
        self._audit(question, packet)
        return packet

    def _supporting_evidence(self, claim_id: str) -> list[dict]:
        with self.db.connect() as con:
            rows = con.execute(
                """
                SELECT l.*, e.title, e.source_type, e.source_uri, e.sha256, s.text AS span_text,
                       s.char_start, s.char_end, s.token_start, s.token_end
                FROM claim_evidence_links l
                JOIN evidence_sources e ON e.id = l.evidence_id
                LEFT JOIN token_spans s ON s.id = l.span_id
                WHERE l.claim_id = ?
                ORDER BY l.created_at DESC
                """,
                (claim_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _contradictions(self, claim_id: str) -> list[dict]:
        with self.db.connect() as con:
            rows = con.execute(
                """
                SELECT * FROM memory_contradictions
                WHERE status = 'unresolved' AND (claim_a_id = ? OR claim_b_id = ?)
                ORDER BY severity DESC, created_at DESC
                """,
                (claim_id, claim_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def _evidence_source(self, evidence_id: str) -> dict | None:
        with self.db.connect() as con:
            row = con.execute("SELECT * FROM evidence_sources WHERE id = ?", (evidence_id,)).fetchone()
        return dict(row) if row else None

    def _audit(self, question: str, packet: ContextPacket) -> None:
        with self.db.connect() as con:
            con.execute(
                "INSERT INTO answer_audit_logs (id, question, context_packet_json, answer_text, warnings_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (new_id("ans"), question, packet.model_dump_json(), None, json_dumps(packet.warnings), now_iso()),
            )
            con.commit()


    def _risk_summary(self, included: list[dict]) -> dict:
        unsupported = 0
        disputed = 0
        pending = 0
        for item in included:
            metadata = item.get("metadata") or {}
            if item.get("kind") == "claim":
                if not item.get("supporting_evidence"):
                    unsupported += 1
                if metadata.get("status") == "disputed":
                    disputed += 1
                if metadata.get("status") == "pending_review":
                    pending += 1
        risk = "low"
        if unsupported or disputed:
            risk = "medium"
        if disputed > 1 or unsupported > 3:
            risk = "high"
        return {"risk": risk, "unsupported_claims": unsupported, "disputed_claims": disputed, "pending_review_claims": pending}
