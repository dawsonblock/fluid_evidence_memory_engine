from __future__ import annotations

from .db import Database, rows_to_dicts


class ProvenanceGraph:
    def __init__(self, db: Database):
        self.db = db

    def trace_claim(self, claim_id: str) -> dict:
        with self.db.connect() as con:
            claim = con.execute("SELECT * FROM memory_claims WHERE id = ?", (claim_id,)).fetchone()
            if not claim:
                raise KeyError(f"claim not found: {claim_id}")
            links = con.execute(
                """
                SELECT l.*, e.project_id, e.source_type, e.title, e.source_uri, e.sha256,
                       ts.text AS span_text, ts.char_start, ts.char_end, ts.token_start, ts.token_end
                FROM claim_evidence_links l
                JOIN evidence_sources e ON e.id = l.evidence_id
                LEFT JOIN token_spans ts ON ts.id = l.span_id
                WHERE l.claim_id = ?
                ORDER BY l.created_at DESC
                """,
                (claim_id,),
            ).fetchall()
            contradictions = con.execute(
                """
                SELECT * FROM memory_contradictions
                WHERE claim_a_id = ? OR claim_b_id = ? ORDER BY severity DESC, created_at DESC
                """,
                (claim_id, claim_id),
            ).fetchall()
            reviews = con.execute("SELECT * FROM review_actions WHERE claim_id = ? ORDER BY created_at DESC", (claim_id,)).fetchall()
            lifecycle = con.execute("SELECT * FROM lifecycle_events WHERE claim_id = ? ORDER BY created_at DESC", (claim_id,)).fetchall()
        return {
            "claim": dict(claim),
            "evidence_links": rows_to_dicts(links),
            "contradictions": rows_to_dicts(contradictions),
            "review_actions": rows_to_dicts(reviews),
            "lifecycle_events": rows_to_dicts(lifecycle),
        }
