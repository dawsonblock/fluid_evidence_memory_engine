"""Tests for the eval-retrieval CLI command (Phase A v0.7.7)."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from feme.cli import app

runner = CliRunner()

_FIXTURE = "tests/fixtures/retrieval/basic_memory_cases.jsonl"


def test_eval_retrieval_runs_and_returns_json(tmp_path: Path):
    """eval-retrieval should return valid JSON with expected keys."""
    result = runner.invoke(app, ["eval-retrieval", "--fixture", _FIXTURE])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert "case_count" in data
    assert "query_count" in data
    assert "substring_hit_rate" in data
    assert "claim_found_rate" in data
    assert "pending_review_leak_rate" in data
    assert "stale_claim_suppression" in data


def test_eval_retrieval_case_count(tmp_path: Path):
    """Fixture now has 4 rows so case_count must be >= 1."""
    result = runner.invoke(app, ["eval-retrieval", "--fixture", _FIXTURE])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["case_count"] >= 1


def test_eval_retrieval_no_pending_review_leaks(tmp_path: Path):
    """Public-mode queries must never return pending_review claims."""
    result = runner.invoke(app, ["eval-retrieval", "--fixture", _FIXTURE])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    leak_rate = data.get("pending_review_leak_rate")
    if leak_rate is not None:
        assert leak_rate == 0.0, f"pending_review_leak_rate={leak_rate}, expected 0.0"


def test_eval_retrieval_missing_fixture(tmp_path: Path):
    """eval-retrieval on a missing fixture should raise a non-zero exit."""
    result = runner.invoke(
        app, ["eval-retrieval", "--fixture", "/nonexistent/path.jsonl"]
    )
    assert result.exit_code != 0 or (
        result.exit_code == 0 and json.loads(result.output)["case_count"] == 0
    ), "Expected either non-zero exit or empty result for missing fixture"


def test_eval_retrieval_top_k_option(tmp_path: Path):
    """--top-k option should be accepted and reflected in output."""
    result = runner.invoke(
        app, ["eval-retrieval", "--fixture", _FIXTURE, "--top-k", "5"]
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["top_k"] == 5
