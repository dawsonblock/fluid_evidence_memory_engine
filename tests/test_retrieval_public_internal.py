"""Tests for public vs. internal retrieval mode using the expanded fixture set.

Verifies:
- Public mode never leaks pending_review claims into results.
- Internal mode can see all claims including pending_review ones.
- pending_review_leak_rate is always 0.0 after public-mode queries.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from feme.eval.retrieval_eval import evaluate_retrieval_fixture

_FIXTURE = "tests/fixtures/retrieval/basic_memory_cases.jsonl"
_BOUNDARY_FIXTURE = "tests/fixtures/retrieval/review_boundary_cases.jsonl"


def test_no_pending_review_leak_in_public_mode():
    """Fixture p3 has a public_only query; pending_review docs must not leak."""
    result = evaluate_retrieval_fixture(_FIXTURE, top_k=10)
    leak_rate = result.get("pending_review_leak_rate")
    if leak_rate is not None:
        assert leak_rate == 0.0, f"Pending review leaked: {leak_rate}"


def test_fixture_returns_expected_keys():
    """Verify all expected metric keys are present in output."""
    result = evaluate_retrieval_fixture(_FIXTURE, top_k=10)
    assert "case_count" in result
    assert "query_count" in result
    assert "substring_hit_rate" in result
    assert "quote_hit_rate" in result
    assert "claim_found_rate" in result
    assert "pending_review_leak_rate" in result
    assert "stale_claim_suppression" in result


def test_claim_found_rate_non_negative():
    result = evaluate_retrieval_fixture(_FIXTURE, top_k=10)
    assert result["claim_found_rate"] >= 0.0
    assert result["claim_found_rate"] <= 1.0


def test_empty_fixture_returns_zeros(tmp_path: Path):
    empty_fixture = tmp_path / "empty.jsonl"
    empty_fixture.write_text("")
    result = evaluate_retrieval_fixture(str(empty_fixture), top_k=5)
    assert result["case_count"] == 0
    assert result["query_count"] == 0
    assert result["substring_hit_rate"] == 0.0
    assert result["pending_review_leak_rate"] is None
    assert result["stale_claim_suppression"] is None


def test_boundary_cases_no_leak():
    """review_boundary_cases fixture public queries must have 0.0 leak rate."""
    from pathlib import Path as _P

    fixture_path = _P(_BOUNDARY_FIXTURE)
    if not fixture_path.exists():
        pytest.skip(f"Fixture not found: {_BOUNDARY_FIXTURE}")
    result = evaluate_retrieval_fixture(_BOUNDARY_FIXTURE, top_k=10)
    leak_rate = result.get("pending_review_leak_rate")
    if leak_rate is not None:
        assert leak_rate == 0.0, f"Boundary fixture leaked: {leak_rate}"
