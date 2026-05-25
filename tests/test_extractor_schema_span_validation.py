from __future__ import annotations

from feme.extractors.schema import validate_extraction_payload


def _claim(**overrides):
    base = {
        "subject": "FEME",
        "predicate": "must_use",
        "object": "PostgreSQL",
        "claim_text": "FEME must use PostgreSQL as canonical memory.",
        "support_char_start": 0,
        "support_char_end": 44,
        "support_quote_text": "FEME must use PostgreSQL as canonical memory.",
    }
    base.update(overrides)
    return base


def test_schema_rejects_quote_mismatch():
    payload = {"claims": [_claim(support_quote_text="wrong quote")]}
    ok, reason = validate_extraction_payload(
        payload,
        source_text="FEME must use PostgreSQL as canonical memory.",
    )
    assert ok is False
    assert "quote_mismatch" in reason


def test_schema_rejects_span_out_of_bounds_with_source_text():
    payload = {"claims": [_claim(support_char_start=0, support_char_end=999)]}
    ok, reason = validate_extraction_payload(payload, source_text="short")
    assert ok is False
    assert "span_out_of_bounds" in reason


def test_schema_rejects_zero_length_span():
    payload = {"claims": [_claim(support_char_start=4, support_char_end=4)]}
    ok, reason = validate_extraction_payload(payload)
    assert ok is False
    assert "zero_length_span" in reason
