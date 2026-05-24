"""Tests for the v0.8 extraction payload schema validator."""
from __future__ import annotations

import pytest

from feme.extractors.schema import (
    CLAIM_EXTRACTION_SCHEMA_VERSION,
    validate_extraction_payload,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_claim(**overrides) -> dict:
    base = {
        "subject": "FEME",
        "predicate": "uses",
        "object": "PostgreSQL",
        "claim_text": "FEME uses PostgreSQL as its backing store.",
        "support_char_start": 0,
        "support_char_end": 40,
    }
    base.update(overrides)
    return base


def _valid_payload(*claims) -> dict:
    return {"claims": list(claims) or [_valid_claim()]}


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

def test_schema_version_constant():
    assert CLAIM_EXTRACTION_SCHEMA_VERSION == "claim-extraction-v1"


# ---------------------------------------------------------------------------
# Top-level payload validation
# ---------------------------------------------------------------------------

def test_valid_minimal_payload():
    ok, reason = validate_extraction_payload(_valid_payload())
    assert ok is True
    assert reason == "ok"


def test_payload_not_a_dict():
    ok, reason = validate_extraction_payload([{"claims": []}])  # type: ignore[arg-type]
    assert ok is False
    assert reason == "payload_not_a_dict"


def test_missing_claims_list():
    ok, reason = validate_extraction_payload({"schema_version": "claim-extraction-v1"})
    assert ok is False
    assert reason == "missing_claims_list"


def test_empty_claims_list():
    ok, reason = validate_extraction_payload({"claims": []})
    assert ok is True
    assert reason == "ok"


def test_candidates_key_accepted_as_alias():
    ok, reason = validate_extraction_payload({"candidates": [_valid_claim()]})
    assert ok is True


def test_support_relation_and_evidence_kind_are_accepted():
    payload = _valid_payload()
    payload["claims"][0]["support_relation"] = "contradicts"
    payload["claims"][0]["evidence_kind"] = "inference"
    ok, reason = validate_extraction_payload(payload)
    assert ok is True
    assert reason == "ok"


def test_legacy_evidence_relation_alias_accepts_non_empty_string():
    payload = _valid_payload()
    payload["claims"][0]["evidence_relation"] = "corroborates_fact"
    ok, reason = validate_extraction_payload(payload)
    assert ok is True
    assert reason == "ok"
    assert reason == "ok"


# ---------------------------------------------------------------------------
# Required string field validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("field", ["subject", "predicate", "object", "claim_text"])
def test_missing_required_str_field(field: str):
    claim = _valid_claim()
    del claim[field]
    ok, reason = validate_extraction_payload(_valid_payload(claim))
    assert ok is False
    assert f"missing_{field}" in reason


@pytest.mark.parametrize("field", ["subject", "predicate", "object", "claim_text"])
def test_empty_required_str_field(field: str):
    ok, reason = validate_extraction_payload(_valid_payload(_valid_claim(**{field: ""})))
    assert ok is False
    assert f"missing_{field}" in reason


@pytest.mark.parametrize("field", ["subject", "predicate", "object", "claim_text"])
def test_whitespace_only_required_str_field(field: str):
    ok, reason = validate_extraction_payload(_valid_payload(_valid_claim(**{field: "   "})))
    assert ok is False
    assert f"missing_{field}" in reason


# ---------------------------------------------------------------------------
# Char span validation
# ---------------------------------------------------------------------------

def test_missing_support_char_start():
    claim = _valid_claim()
    del claim["support_char_start"]
    ok, reason = validate_extraction_payload(_valid_payload(claim))
    assert ok is False
    assert "support_char_start" in reason


def test_missing_support_char_end():
    claim = _valid_claim()
    del claim["support_char_end"]
    ok, reason = validate_extraction_payload(_valid_payload(claim))
    assert ok is False
    assert "support_char_end" in reason


def test_negative_char_start():
    ok, reason = validate_extraction_payload(_valid_payload(_valid_claim(support_char_start=-1)))
    assert ok is False
    assert "support_char_start_negative" in reason


def test_char_end_not_after_start():
    ok, reason = validate_extraction_payload(
        _valid_payload(_valid_claim(support_char_start=10, support_char_end=10))
    )
    assert ok is False
    assert "support_char_end_not_after_start" in reason


def test_char_end_before_start():
    ok, reason = validate_extraction_payload(
        _valid_payload(_valid_claim(support_char_start=20, support_char_end=5))
    )
    assert ok is False
    assert "support_char_end_not_after_start" in reason


# ---------------------------------------------------------------------------
# Token span validation
# ---------------------------------------------------------------------------

def test_valid_token_span():
    claim = _valid_claim(support_token_start=0, support_token_end=8)
    ok, reason = validate_extraction_payload(_valid_payload(claim))
    assert ok is True


def test_partial_token_span_only_start():
    claim = _valid_claim(support_token_start=0)
    ok, reason = validate_extraction_payload(_valid_payload(claim))
    assert ok is False
    assert "partial_token_span" in reason


def test_partial_token_span_only_end():
    claim = _valid_claim(support_token_end=8)
    ok, reason = validate_extraction_payload(_valid_payload(claim))
    assert ok is False
    assert "partial_token_span" in reason


def test_token_span_not_int():
    claim = _valid_claim(support_token_start="0", support_token_end="8")
    ok, reason = validate_extraction_payload(_valid_payload(claim))
    assert ok is False
    assert "token_span_not_int" in reason


def test_invalid_token_span_range():
    claim = _valid_claim(support_token_start=5, support_token_end=3)
    ok, reason = validate_extraction_payload(_valid_payload(claim))
    assert ok is False
    assert "invalid_token_span_range" in reason


# ---------------------------------------------------------------------------
# Optional float field validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("field", [
    "confidence", "salience", "user_explicitness", "long_term_usefulness",
    "project_relevance", "actionability", "contradiction_value",
    "uncertainty", "triviality", "short_livedness",
])
def test_valid_float_field(field: str):
    ok, reason = validate_extraction_payload(_valid_payload(_valid_claim(**{field: 0.75})))
    assert ok is True


@pytest.mark.parametrize("field", ["confidence", "salience"])
def test_float_field_out_of_range_high(field: str):
    ok, reason = validate_extraction_payload(_valid_payload(_valid_claim(**{field: 1.5})))
    assert ok is False
    assert "out_of_range" in reason


@pytest.mark.parametrize("field", ["confidence", "salience"])
def test_float_field_out_of_range_low(field: str):
    ok, reason = validate_extraction_payload(_valid_payload(_valid_claim(**{field: -0.1})))
    assert ok is False
    assert "out_of_range" in reason


@pytest.mark.parametrize("field", ["confidence", "salience"])
def test_float_field_not_numeric(field: str):
    ok, reason = validate_extraction_payload(_valid_payload(_valid_claim(**{field: "high"})))
    assert ok is False
    assert "not_numeric" in reason


def test_float_field_int_value_accepted():
    ok, reason = validate_extraction_payload(_valid_payload(_valid_claim(confidence=1)))
    assert ok is True


# ---------------------------------------------------------------------------
# Optional field type checks
# ---------------------------------------------------------------------------

def test_support_quote_text_not_str():
    ok, reason = validate_extraction_payload(
        _valid_payload(_valid_claim(support_quote_text=42))
    )
    assert ok is False
    assert "support_quote_text_not_str" in reason


def test_support_quote_text_valid():
    ok, reason = validate_extraction_payload(
        _valid_payload(_valid_claim(support_quote_text="FEME uses PostgreSQL"))
    )
    assert ok is True


def test_metadata_not_dict():
    ok, reason = validate_extraction_payload(
        _valid_payload(_valid_claim(metadata=["tag1", "tag2"]))
    )
    assert ok is False
    assert "metadata_not_dict" in reason


def test_metadata_valid():
    ok, reason = validate_extraction_payload(
        _valid_payload(_valid_claim(metadata={"source": "llm", "version": "1"}))
    )
    assert ok is True


# ---------------------------------------------------------------------------
# Multi-claim payload
# ---------------------------------------------------------------------------

def test_multiple_valid_claims():
    claims = [
        _valid_claim(subject="FEME", predicate="uses", object="PostgreSQL"),
        _valid_claim(
            subject="FEME",
            predicate="supports",
            object="SQLite",
            claim_text="FEME also supports SQLite for local development.",
            support_char_start=0,
            support_char_end=46,
        ),
    ]
    ok, reason = validate_extraction_payload({"claims": claims})
    assert ok is True


def test_second_claim_invalid_fails_with_index():
    claims = [
        _valid_claim(),
        _valid_claim(support_char_start=-5),
    ]
    ok, reason = validate_extraction_payload({"claims": claims})
    assert ok is False
    assert "claim[1]" in reason


def test_claim_entry_not_a_dict():
    ok, reason = validate_extraction_payload({"claims": [_valid_claim(), "bad_entry"]})
    assert ok is False
    assert "not_a_dict" in reason
