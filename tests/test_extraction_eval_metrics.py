from __future__ import annotations

from pathlib import Path

from feme.eval import evaluate_extraction_fixture


def test_extraction_eval_reports_quality_metric_keys():
    fixture = Path("tests/fixtures/extraction/project_decisions.jsonl")
    result = evaluate_extraction_fixture(str(fixture), extractor_mode="heuristic")

    required = {
        "false_positive_rate",
        "false_negative_rate",
        "precision",
        "recall",
        "f1",
        "direct_kind_accuracy",
        "inference_kind_accuracy",
        "summary_kind_accuracy",
        "support_relation_accuracy",
        "multi_claim_count_accuracy",
        "evidence_kind_accuracy",
    }
    assert required.issubset(result.keys())


def test_extraction_eval_no_claim_noise_has_bounded_false_positive_rate():
    fixture = Path("tests/fixtures/extraction/no_claim_noise.jsonl")
    result = evaluate_extraction_fixture(str(fixture), extractor_mode="heuristic")

    assert result["false_positive_rate"] <= 0.15


def test_extraction_eval_debug_report_contains_misses_and_span_errors():
    fixture = Path("tests/fixtures/extraction/legal_style_claims.jsonl")
    result = evaluate_extraction_fixture(
        str(fixture),
        extractor_mode="heuristic",
        debug=True,
        debug_spans=True,
    )

    assert "cases" in result
    assert isinstance(result["cases"], list)
    assert "misses" in result["cases"][0]
    assert "false_positives" in result["cases"][0]
    assert "span_errors" in result["cases"][0]
    assert "span_debug" in result
