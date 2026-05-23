from pathlib import Path

from feme.eval import evaluate_extraction_fixture


def test_extraction_eval_returns_metrics_for_fixture():
    fixture = Path("tests/fixtures/extraction/project_decisions.jsonl")
    result = evaluate_extraction_fixture(str(fixture), extractor_mode="heuristic")

    assert result["case_count"] >= 1
    assert "claim_count_accuracy" in result
    assert "support_span_exact_match" in result
    assert "quote_exact_match" in result


def test_extraction_eval_strict_rejection_fixture():
    fixture = Path("tests/fixtures/extraction/quote_mismatch_cases.jsonl")
    result = evaluate_extraction_fixture(
        str(fixture),
        extractor_mode="json_strict",
        extractor_provider="json_static",
    )

    assert result["case_count"] == 1
    assert result["strict_rejection_rate"] == 1.0
