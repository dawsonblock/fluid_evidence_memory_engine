from __future__ import annotations

from .db import Database
from .models import EvaluationCase
from .retrieval import RetrievalPlanner
from .utils import json_dumps, new_id, now_iso


class RetrievalEvaluator:
    def __init__(self, db: Database):
        self.db = db
        self.retrieval = RetrievalPlanner(db)

    def run_case(self, case: EvaluationCase, *, top_k: int = 10) -> dict:
        results = self.retrieval.search(case.query, project_id=case.project_id, top_k=top_k)
        result_claim_ids = [r.claim_id for r in results if r.claim_id]
        hit_claims = [cid for cid in case.expected_claim_ids if cid in result_claim_ids]
        result_text = "\n".join(r.text.lower() for r in results)
        hit_terms = [term for term in case.expected_terms if term.lower() in result_text]
        score_parts = []
        if case.expected_claim_ids:
            score_parts.append(len(hit_claims) / len(case.expected_claim_ids))
        if case.expected_terms:
            score_parts.append(len(hit_terms) / len(case.expected_terms))
        score = sum(score_parts) / len(score_parts) if score_parts else 0.0
        result = {
            "case_id": case.id,
            "score": score,
            "hit_claims": hit_claims,
            "hit_terms": hit_terms,
            "result_ids": [r.id for r in results],
        }
        with self.db.connect() as con:
            con.execute(
                "INSERT INTO evaluation_runs (id, project_id, case_json, result_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (new_id("eval"), case.project_id, case.model_dump_json(), json_dumps(result), now_iso()),
            )
            con.commit()
        return result
