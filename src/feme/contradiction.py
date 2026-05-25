from __future__ import annotations

from contextlib import nullcontext

from .db import Database
from .utils import new_id, normalize_key, now_iso

NEGATION_TERMS = {
    "not",
    "no",
    "never",
    "cannot",
    "can't",
    "isn't",
    "wasn't",
    "won't",
    "without",
}
OPPOSITE_PREDICATES = {
    ("is", "is_not"),
    ("allowed", "not_allowed"),
    ("must_use", "must_not_use"),
    ("should_use", "should_not_use"),
}


class ContradictionEngine:
    def __init__(self, db: Database):
        self.db = db

    def scan_new_claim(
        self, claim_id: str, *, con=None, autocommit: bool = True
    ) -> list[dict]:
        con_ctx = nullcontext(con) if con is not None else self.db.connect()
        with con_ctx as active_con:
            claim = active_con.execute(
                "SELECT * FROM memory_claims WHERE id = ?", (claim_id,)
            ).fetchone()
            if not claim:
                return []
            candidates = active_con.execute(
                """
                SELECT * FROM memory_claims
                WHERE id != ? AND project_id = ? AND status IN ('active', 'pending_review', 'disputed')
                AND lower(subject) = lower(?)
                """,
                (claim_id, claim["project_id"], claim["subject"]),
            ).fetchall()
        out = []
        for other in candidates:
            detection = self.detect(dict(claim), dict(other))
            if detection:
                self.record(
                    claim_id, other["id"], detection, con=con, autocommit=autocommit
                )
                out.append(detection | {"other_claim_id": other["id"]})
        return out

    def detect(self, a: dict, b: dict) -> dict | None:
        if normalize_key(a["subject"]) != normalize_key(b["subject"]):
            return None
        same_pred = normalize_key(a["predicate"]) == normalize_key(b["predicate"])
        object_diff = normalize_key(a["object"]) != normalize_key(b["object"])
        neg_a = _has_negation(a["claim_text"])
        neg_b = _has_negation(b["claim_text"])
        if (
            same_pred
            and object_diff
            and (neg_a != neg_b or _conflicting_objects(a["object"], b["object"]))
        ):
            return {
                "contradiction_type": "same_subject_predicate_conflicting_object",
                "severity": 0.75,
                "explanation": "Claims share a subject/predicate but differ in object or negation.",
            }
        if neg_a != neg_b and _overlap(a["claim_text"], b["claim_text"]) >= 0.45:
            return {
                "contradiction_type": "textual_negation_conflict",
                "severity": 0.65,
                "explanation": "Claims have overlapping wording but opposite negation polarity.",
            }
        return None

    def record(
        self,
        claim_a_id: str,
        claim_b_id: str,
        detection: dict,
        *,
        con=None,
        autocommit: bool = True,
    ) -> None:
        now = now_iso()
        con_ctx = nullcontext(con) if con is not None else self.db.connect()
        with con_ctx as active_con:
            existing = active_con.execute(
                """
                SELECT id FROM memory_contradictions
                WHERE (claim_a_id = ? AND claim_b_id = ?) OR (claim_a_id = ? AND claim_b_id = ?)
                """,
                (claim_a_id, claim_b_id, claim_b_id, claim_a_id),
            ).fetchone()
            if existing:
                return
            active_con.execute(
                """
                INSERT INTO memory_contradictions
                (id, claim_a_id, claim_b_id, contradiction_type, severity, status, explanation, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id("contra"),
                    claim_a_id,
                    claim_b_id,
                    detection["contradiction_type"],
                    detection["severity"],
                    "unresolved",
                    detection["explanation"],
                    now,
                ),
            )
            active_con.execute(
                "UPDATE memory_claims SET status = 'disputed', updated_at = ? WHERE id IN (?, ?)",
                (now, claim_a_id, claim_b_id),
            )
            if autocommit:
                active_con.commit()


def _has_negation(text: str) -> bool:
    words = {w.strip(".,;:!?()[]{}\"'").lower() for w in text.split()}
    return bool(words & NEGATION_TERMS)


def _conflicting_objects(a: str, b: str) -> bool:
    aa = normalize_key(a)
    bb = normalize_key(b)
    if aa == bb:
        return False
    if aa in {"true", "yes", "allowed", "enabled"} and bb in {
        "false",
        "no",
        "not_allowed",
        "disabled",
    }:
        return True
    if bb in {"true", "yes", "allowed", "enabled"} and aa in {
        "false",
        "no",
        "not_allowed",
        "disabled",
    }:
        return True
    return False


def _overlap(a: str, b: str) -> float:
    aw = {w.lower() for w in a.split() if len(w) > 3}
    bw = {w.lower() for w in b.split() if len(w) > 3}
    if not aw or not bw:
        return 0.0
    return len(aw & bw) / max(1, len(aw | bw))
