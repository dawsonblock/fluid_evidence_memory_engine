from __future__ import annotations

import hashlib

from .db import Database
from .models import EvaluationCase
from .retrieval import RetrievalPlanner
from .utils import json_dumps, new_id, now_iso


class RetrievalEvaluator:
    def __init__(self, db: Database):
        self.db = db
        self.retrieval = RetrievalPlanner(db)

    def run_case(self, case: EvaluationCase, *, top_k: int = 10) -> dict:
        results = self.retrieval.search(
            case.query, project_id=case.project_id, top_k=top_k
        )
        result_claim_ids = [r.claim_id for r in results if r.claim_id]
        hit_claims = [cid for cid in case.expected_claim_ids if cid in result_claim_ids]
        result_text = "\n".join(r.text.lower() for r in results)
        hit_terms = [
            term for term in case.expected_terms if term.lower() in result_text
        ]
        score_parts = []
        if case.expected_claim_ids:
            score_parts.append(len(hit_claims) / len(case.expected_claim_ids))
        if case.expected_terms:
            score_parts.append(len(hit_terms) / len(case.expected_terms))
        score = sum(score_parts) / len(score_parts) if score_parts else 0.0
        span_metrics = self._citation_span_metrics(results)
        result = {
            "case_id": case.id,
            "score": score,
            "hit_claims": hit_claims,
            "hit_terms": hit_terms,
            "result_ids": [r.id for r in results],
            "span_metrics": span_metrics,
        }
        with self.db.connect() as con:
            con.execute(
                "INSERT INTO evaluation_runs (id, project_id, case_json, result_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    new_id("eval"),
                    case.project_id,
                    case.model_dump_json(),
                    json_dumps(result),
                    now_iso(),
                ),
            )
            con.commit()
        return result

    def _citation_span_metrics(self, results: list) -> dict:
        claim_ids = [r.claim_id for r in results if r.claim_id]
        chunk_ids = [r.chunk_id for r in results if r.kind == "chunk" and r.chunk_id]
        claim_ids = list(dict.fromkeys(claim_ids))
        chunk_ids = list(dict.fromkeys(chunk_ids))

        metrics = {
            "total_spans": 0,
            "char_bounds_valid": 0,
            "token_bounds_valid": 0,
            "quote_hash_checked": 0,
            "quote_hash_valid": 0,
        }

        with self.db.connect() as con:
            if claim_ids:
                ph = ",".join("?" for _ in claim_ids)
                rows = con.execute(
                    f"""
                    SELECT char_start, char_end, token_start, token_end, quote_sha256 AS hash_value, quote_text AS text_value
                    FROM claim_support_spans
                    WHERE claim_id IN ({ph})
                    """,
                    claim_ids,
                ).fetchall()
                for row in rows:
                    self._accumulate_span_metrics(metrics, row)

            if chunk_ids:
                ph = ",".join("?" for _ in chunk_ids)
                rows = con.execute(
                    f"""
                    SELECT char_start, char_end, token_start, token_end, text_sha256 AS hash_value, text AS text_value
                    FROM token_spans
                    WHERE chunk_id IN ({ph})
                    """,
                    chunk_ids,
                ).fetchall()
                for row in rows:
                    self._accumulate_span_metrics(metrics, row)

        total = metrics["total_spans"]
        metrics["char_bounds_valid_ratio"] = (
            metrics["char_bounds_valid"] / total if total else 0.0
        )
        metrics["token_bounds_valid_ratio"] = (
            metrics["token_bounds_valid"] / total if total else 0.0
        )
        checked = metrics["quote_hash_checked"]
        metrics["quote_hash_valid_ratio"] = (
            metrics["quote_hash_valid"] / checked if checked else 0.0
        )
        return metrics

    @staticmethod
    def _accumulate_span_metrics(metrics: dict, row) -> None:
        metrics["total_spans"] += 1

        char_start = row["char_start"]
        char_end = row["char_end"]
        token_start = row["token_start"]
        token_end = row["token_end"]
        hash_value = row["hash_value"]
        text_value = row["text_value"]

        if _valid_char_bounds(char_start, char_end):
            metrics["char_bounds_valid"] += 1
        if _valid_token_bounds(token_start, token_end):
            metrics["token_bounds_valid"] += 1

        if hash_value and text_value is not None:
            metrics["quote_hash_checked"] += 1
            actual = hashlib.sha256(str(text_value).encode("utf-8")).hexdigest()
            if actual == str(hash_value):
                metrics["quote_hash_valid"] += 1


def _valid_char_bounds(start, end) -> bool:
    return (
        isinstance(start, int) and isinstance(end, int) and start >= 0 and end > start
    )


def _valid_token_bounds(start, end) -> bool:
    return (
        isinstance(start, int) and isinstance(end, int) and start >= 0 and end >= start
    )
