from __future__ import annotations

from pathlib import Path

from feme.eval.fixture_validator import validate_extraction_fixture_file


def test_fixture_validator_accepts_project_decisions_fixture():
    fixture = Path("tests/fixtures/extraction/project_decisions.jsonl")
    result = validate_extraction_fixture_file(str(fixture))
    assert result["valid"] is True
    assert result["error_count"] == 0


def test_fixture_validator_rejects_bad_quote_slice(tmp_path: Path):
    fixture = tmp_path / "bad_fixture.jsonl"
    fixture.write_text(
        (
            '{"case_id":"c1","text":"abc","expected_claims":['
            '{"claim_text":"ab","char_start":0,"char_end":2,'
            '"support_quote_text":"zz"}]}\n'
        ),
        encoding="utf-8",
    )

    result = validate_extraction_fixture_file(str(fixture))
    assert result["valid"] is False
    assert result["error_count"] == 1
    assert result["errors"][0]["reason"] == "expected_quote_span_mismatch"


def test_fixture_validator_rejects_missing_case_id(tmp_path: Path):
    fixture = tmp_path / "missing_case.jsonl"
    fixture.write_text(
        '{"text":"abc","expected_claims":[]}\n',
        encoding="utf-8",
    )
    result = validate_extraction_fixture_file(str(fixture))
    assert result["valid"] is False
    assert any(err["reason"] == "missing_case_id" for err in result["errors"])


def test_fixture_validator_rejects_duplicate_case_id(tmp_path: Path):
    fixture = tmp_path / "duplicate_case.jsonl"
    fixture.write_text(
        '{"case_id":"dup","text":"a","expected_claims":[]}\n'
        '{"case_id":"dup","text":"b","expected_claims":[]}\n',
        encoding="utf-8",
    )
    result = validate_extraction_fixture_file(str(fixture))
    assert result["valid"] is False
    assert any(err["reason"] == "duplicate_case_id" for err in result["errors"])


def test_fixture_validator_rejects_missing_expected_claims(tmp_path: Path):
    fixture = tmp_path / "missing_expected.jsonl"
    fixture.write_text(
        '{"case_id":"missing_expected","text":"abc"}\n',
        encoding="utf-8",
    )
    result = validate_extraction_fixture_file(str(fixture))
    assert result["valid"] is False
    assert any(err["reason"] == "missing_expected_claims" for err in result["errors"])
