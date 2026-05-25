from __future__ import annotations

from pathlib import Path

from feme.eval.retrieval_eval import evaluate_retrieval_fixture


def test_eval_retrieval_quote_hit_rate_uses_support_spans_fixture():
    fixture = Path("tests/fixtures/retrieval/basic_memory_cases.jsonl")
    result = evaluate_retrieval_fixture(str(fixture))

    assert result["claim_found_rate"] == 1.0
    assert result["quote_hit_rate"] == 1.0
    assert result["pending_review_leak_rate"] == 0.0
