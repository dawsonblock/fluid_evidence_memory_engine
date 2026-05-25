from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class SpanMatch:
    char_start: int
    char_end: int
    quote: str
    exact: bool
    occurrence_index: int = 0


def normalize_for_span_compare(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def find_exact_quote_span(
    source_text: str,
    quote: str,
    occurrence_index: int = 0,
) -> SpanMatch | None:
    if not isinstance(source_text, str) or not isinstance(quote, str):
        return None
    if not quote:
        return None
    if occurrence_index < 0:
        return None

    cursor = 0
    found_count = -1
    while True:
        idx = source_text.find(quote, cursor)
        if idx < 0:
            return None
        found_count += 1
        if found_count == occurrence_index:
            end = idx + len(quote)
            return SpanMatch(
                char_start=idx,
                char_end=end,
                quote=quote,
                exact=source_text[idx:end] == quote,
                occurrence_index=occurrence_index,
            )
        cursor = idx + 1


def validate_span(source_text: str, char_start: int, char_end: int, quote: str) -> bool:
    if not isinstance(source_text, str) or not isinstance(quote, str):
        return False
    if not isinstance(char_start, int) or not isinstance(char_end, int):
        return False
    if char_start < 0 or char_end < 0 or char_end <= char_start:
        return False
    if char_end > len(source_text):
        return False
    return source_text[char_start:char_end] == quote


def repair_span_from_quote(source_text: str, quote: str) -> SpanMatch | None:
    # Deterministic repair: choose the first exact occurrence when present.
    return find_exact_quote_span(source_text, quote, occurrence_index=0)
