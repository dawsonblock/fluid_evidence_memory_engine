"""Tests for feme.eval.retrieval_eval harness and the Phase 3 fixture files."""
from __future__ import annotations

import json
import os

import pytest

from feme.eval.retrieval_eval import evaluate_retrieval_fixture

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "retrieval")


def _fixture(name: str) -> str:
    return os.path.join(FIXTURE_DIR, name)


# ---------------------------------------------------------------------------
# Smoke tests: return type and key structure
# ---------------------------------------------------------------------------

def test_returns_expected_keys():
    result = evaluate_retrieval_fixture(_fixture("basic_memory_cases.jsonl"))
    expected_keys = {
        "fixture_path",
        "case_count",
        "query_count",
        "substring_hit_rate",
        "quote_hit_rate",
        "extractor_mode",
        "top_k",
    }
    assert expected_keys.issubset(result.keys())


def test_substring_hit_rate_is_float_in_unit_interval():
    result = evaluate_retrieval_fixture(_fixture("basic_memory_cases.jsonl"))
    rate = result["substring_hit_rate"]
    assert isinstance(rate, float)
    assert 0.0 <= rate <= 1.0


def test_quote_hit_rate_is_float_in_unit_interval():
    result = evaluate_retrieval_fixture(_fixture("basic_memory_cases.jsonl"))
    rate = result["quote_hit_rate"]
    assert isinstance(rate, float)
    assert 0.0 <= rate <= 1.0


# ---------------------------------------------------------------------------
# basic_memory_cases.jsonl
# ---------------------------------------------------------------------------

def test_basic_memory_cases_case_count():
    result = evaluate_retrieval_fixture(_fixture("basic_memory_cases.jsonl"))
    assert result["case_count"] == 1


def test_basic_memory_cases_query_count():
    result = evaluate_retrieval_fixture(_fixture("basic_memory_cases.jsonl"))
    assert result["query_count"] >= 1


def test_basic_memory_cases_extractor_mode_default():
    result = evaluate_retrieval_fixture(_fixture("basic_memory_cases.jsonl"))
    assert result["extractor_mode"] == "heuristic"


def test_basic_memory_cases_top_k_default():
    result = evaluate_retrieval_fixture(_fixture("basic_memory_cases.jsonl"))
    assert result["top_k"] == 10


# ---------------------------------------------------------------------------
# review_boundary_cases.jsonl
# ---------------------------------------------------------------------------

def test_review_boundary_cases_case_count():
    result = evaluate_retrieval_fixture(_fixture("review_boundary_cases.jsonl"))
    assert result["case_count"] == 2


def test_review_boundary_cases_query_count():
    result = evaluate_retrieval_fixture(_fixture("review_boundary_cases.jsonl"))
    assert result["query_count"] >= 2


# ---------------------------------------------------------------------------
# citation_span_cases.jsonl
# ---------------------------------------------------------------------------

def test_citation_span_cases_case_count():
    result = evaluate_retrieval_fixture(_fixture("citation_span_cases.jsonl"))
    assert result["case_count"] == 2


# ---------------------------------------------------------------------------
# contradiction_cases.jsonl
# ---------------------------------------------------------------------------

def test_contradiction_cases_case_count():
    result = evaluate_retrieval_fixture(_fixture("contradiction_cases.jsonl"))
    assert result["case_count"] == 2


# ---------------------------------------------------------------------------
# Empty fixture edge case
# ---------------------------------------------------------------------------

def test_empty_fixture_returns_zeros(tmp_path):
    empty = tmp_path / "empty.jsonl"
    empty.write_text("\n", encoding="utf-8")
    result = evaluate_retrieval_fixture(str(empty))
    assert result["case_count"] == 0
    assert result["query_count"] == 0
    assert result["substring_hit_rate"] == 0.0
    assert result["quote_hit_rate"] == 0.0


def test_empty_fixture_no_keys_for_mode_and_top_k(tmp_path):
    """When case_count==0 the result should still be a dict without errors."""
    empty = tmp_path / "e.jsonl"
    empty.write_text("", encoding="utf-8")
    result = evaluate_retrieval_fixture(str(empty))
    assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Custom parameters forwarded
# ---------------------------------------------------------------------------

def test_top_k_parameter_forwarded():
    result = evaluate_retrieval_fixture(
        _fixture("basic_memory_cases.jsonl"), top_k=5
    )
    assert result["top_k"] == 5


def test_extractor_mode_parameter_forwarded():
    result = evaluate_retrieval_fixture(
        _fixture("basic_memory_cases.jsonl"), extractor_mode="heuristic"
    )
    assert result["extractor_mode"] == "heuristic"
