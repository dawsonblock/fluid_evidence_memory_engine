from __future__ import annotations

from feme.spans import (
    find_exact_quote_span,
    normalize_for_span_compare,
    repair_span_from_quote,
    validate_span,
)


def test_find_exact_quote_span_basic():
    text = "FEME must use PostgreSQL as canonical memory."
    match = find_exact_quote_span(text, "PostgreSQL")
    assert match is not None
    assert match.char_start == 14
    assert match.char_end == 24
    assert match.exact is True


def test_find_exact_quote_span_at_start_and_end():
    text = "alpha beta"
    start = find_exact_quote_span(text, "alpha")
    end = find_exact_quote_span(text, "beta")
    assert start is not None and start.char_start == 0
    assert end is not None and end.char_end == len(text)


def test_find_exact_quote_span_after_leading_whitespace():
    text = "   FEME keeps audit rows"
    match = find_exact_quote_span(text, "FEME")
    assert match is not None
    assert match.char_start == 3


def test_find_exact_quote_span_duplicate_occurrence_index():
    text = "repeat here; repeat there"
    first = find_exact_quote_span(text, "repeat", occurrence_index=0)
    second = find_exact_quote_span(text, "repeat", occurrence_index=1)
    assert first is not None and second is not None
    assert first.char_start == 0
    assert second.char_start > first.char_start


def test_find_exact_quote_span_mismatch_returns_none():
    assert find_exact_quote_span("abc", "zzz") is None


def test_validate_span_true_when_slice_matches():
    text = "abcdef"
    assert validate_span(text, 1, 4, "bcd") is True


def test_validate_span_false_when_slice_differs():
    text = "abcdef"
    assert validate_span(text, 1, 4, "xxx") is False


def test_repair_span_from_quote_returns_first_occurrence():
    text = "quote A and quote A again"
    match = repair_span_from_quote(text, "quote A")
    assert match is not None
    assert match.char_start == 0


def test_normalize_for_span_compare_collapses_whitespace():
    assert normalize_for_span_compare(" a\n b\t c ") == "a b c"
