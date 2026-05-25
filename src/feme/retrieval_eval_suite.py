from __future__ import annotations

import json

from .db import Database
from .evaluation import RetrievalEvaluator
from .models import EvaluationCase
from .utils import json_dumps, new_id, now_iso


class RetrievalEvalSuite:
    def __init__(self, db: Database):
        self.db = db

    def add_case(
        self,
        *,
        query: str,
        expected_claim_ids: list[str] | None = None,
        expected_terms: list[str] | None = None,
        project_id: str = "default",
        metadata: dict | None = None,
    ) -> dict:
        case_id = new_id("evalcase")
        with self.db.connect() as con:
            con.execute(
                """
                INSERT INTO retrieval_eval_cases
                (id, project_id, query, expected_claim_ids_json, expected_terms_json, created_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    case_id,
                    project_id,
                    query,
                    json_dumps(expected_claim_ids or []),
                    json_dumps(expected_terms or []),
                    now_iso(),
                    json_dumps(metadata or {}),
                ),
            )
            con.commit()
        return {"id": case_id, "project_id": project_id, "query": query}

    def list_cases(self, *, project_id: str = "default") -> list[dict]:
        with self.db.connect() as con:
            rows = con.execute(
                "SELECT * FROM retrieval_eval_cases WHERE project_id = ? ORDER BY created_at",
                (project_id,),
            ).fetchall()
        out: list[dict] = []
        for row in rows:
            item = dict(row)
            item["expected_claim_ids"] = json.loads(
                item.pop("expected_claim_ids_json") or "[]"
            )
            item["expected_terms"] = json.loads(item.pop("expected_terms_json") or "[]")
            item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
            out.append(item)
        return out

    def run(self, *, project_id: str = "default", top_k: int = 10) -> dict:
        cases = self.list_cases(project_id=project_id)
        evaluator = RetrievalEvaluator(self.db)
        results = []
        for case in cases:
            model_case = EvaluationCase(
                id=case["id"],
                query=case["query"],
                expected_claim_ids=case["expected_claim_ids"],
                expected_terms=case["expected_terms"],
                project_id=project_id,
            )
            result = evaluator.run_case(model_case, top_k=top_k)
            result["passed"] = result.get("score", 0.0) >= 1.0
            results.append(result)
        total = len(results)
        passed = sum(1 for r in results if r.get("passed"))
        return {
            "project_id": project_id,
            "case_count": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": passed / total if total else 0.0,
            "results": results,
        }
