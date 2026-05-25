from __future__ import annotations

from feme.extractors.repair import repair_payload_span_offsets


TEXT = "FEME must use PostgreSQL as canonical memory."


def _payload(start: int, end: int, quote: str = TEXT):
    return {
        "claims": [
            {
                "subject": "FEME",
                "predicate": "must_use",
                "object": "PostgreSQL as canonical memory",
                "claim_text": TEXT,
                "support_char_start": start,
                "support_char_end": end,
                "support_quote_text": quote,
            }
        ]
    }


def test_repair_span_offsets_repairs_single_occurrence_quote():
    payload, repaired, reason = repair_payload_span_offsets(
        _payload(1, len(TEXT)),
        source_text=TEXT,
        require_unique_quote=True,
    )
    assert reason is None
    assert repaired is True
    claim = payload["claims"][0]
    assert claim["support_char_start"] == 0
    assert claim["support_char_end"] == len(TEXT)


def test_repair_span_offsets_fails_when_quote_missing():
    payload, repaired, reason = repair_payload_span_offsets(
        _payload(0, 5, quote="missing"),
        source_text=TEXT,
        require_unique_quote=True,
    )
    assert repaired is False
    assert reason is not None
    assert "span_repair_failed" in reason


def test_repair_span_offsets_fails_when_ambiguous_and_unique_required():
    text = "repeat and repeat"
    payload = _payload(1, 7, quote="repeat")
    payload, repaired, reason = repair_payload_span_offsets(
        payload,
        source_text=text,
        require_unique_quote=True,
    )
    assert repaired is False
    assert reason is not None
    assert "span_repair_ambiguous" in reason
