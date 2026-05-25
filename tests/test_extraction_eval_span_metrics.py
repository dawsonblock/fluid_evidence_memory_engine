from __future__ import annotations

from pathlib import Path

from feme.eval import evaluate_extraction_fixture


def test_extraction_eval_reports_new_span_metrics():
    fixture = Path("tests/fixtures/extraction/project_decisions.jsonl")
    result = evaluate_extraction_fixture(str(fixture), extractor_mode="heuristic")

    assert "support_span_exact_match" in result
    assert "support_quote_exact_match" in result
    assert "support_span_validity_rate" in result
    assert "quote_exact_match" in result
    assert result["support_quote_exact_match"] == result["quote_exact_match"]


def test_extraction_eval_debug_spans_includes_diagnostics():
    fixture = Path("tests/fixtures/extraction/project_decisions.jsonl")
    result = evaluate_extraction_fixture(
        str(fixture), extractor_mode="heuristic", debug_spans=True
    )

    assert "span_debug" in result
    assert isinstance(result["span_debug"], list)
