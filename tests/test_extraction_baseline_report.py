from __future__ import annotations

from pathlib import Path

from feme.eval import evaluate_extraction_fixture


def test_extraction_baseline_report_includes_required_metric_keys():
    fixture = Path("tests/fixtures/extraction/project_decisions.jsonl")
    result = evaluate_extraction_fixture(
        str(fixture),
        extractor_mode="heuristic",
    )

    required_keys = {
        "case_count",
        "claim_count_accuracy",
        "support_span_exact_match",
        "quote_exact_match",
        "fallback_rate",
        "strict_rejection_rate",
    }
    assert required_keys.issubset(result.keys())


def test_eval_extraction_verbose_reports_case_details():
    payload = evaluate_extraction_fixture(
        "tests/fixtures/extraction/project_decisions.jsonl",
        extractor_mode="heuristic",
        verbose=True,
    )

    assert payload["case_count"] >= 1
    assert isinstance(payload["cases"], list)
    assert "source_text" in payload["cases"][0]
    assert "miss_reason" in payload["cases"][0]