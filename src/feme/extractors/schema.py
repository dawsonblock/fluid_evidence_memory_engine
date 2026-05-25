"""Extraction payload schema validator for FEME v0.8+.

Validates structured JSON payloads produced by extractor providers before they
are passed to _structured_candidates_from_json.  The validator enforces the
``claim-extraction-v1`` contract; future schema versions can extend or replace
this module without touching the core extractor pipeline.
"""

from __future__ import annotations

from typing import Any

from ..spans import validate_span

_VALID_EVIDENCE_KINDS = {"direct", "inference", "summary", "unknown"}
_VALID_SUPPORT_RELATIONS = {
    "supports",
    "contradicts",
    "summarizes",
    "mentions",
    "inferred_from",
    "unknown",
}

CLAIM_EXTRACTION_SCHEMA_VERSION = "claim-extraction-v1"

# Required string fields on every claim entry
_REQUIRED_STR_FIELDS: tuple[str, ...] = (
    "subject",
    "predicate",
    "object",
    "claim_text",
)

# Required integer span fields on every claim entry
_REQUIRED_SPAN_FIELDS: tuple[str, ...] = (
    "support_char_start",
    "support_char_end",
)

# Optional float fields – if present they must be in [0.0, 1.0]
_OPTIONAL_FLOAT_FIELDS: tuple[str, ...] = (
    "confidence",
    "salience",
    "user_explicitness",
    "long_term_usefulness",
    "project_relevance",
    "actionability",
    "contradiction_value",
    "uncertainty",
    "triviality",
    "short_livedness",
)


def validate_extraction_payload(
    payload: dict[str, Any],
    *,
    source_text: str | None = None,
) -> tuple[bool, str]:
    """Validate a structured extraction payload against the v1 schema.

    Parameters
    ----------
    payload:
        The raw dict returned by an :class:`~feme.extractors.base.ExtractorProvider`.
    source_text:
        When provided, each claim's ``support_quote_text`` is verified against
        ``source_text[support_char_start:support_char_end]``.

    Returns
    -------
    (ok, reason)
        ``ok`` is *True* when the payload is valid.  When *False*, ``reason``
        is a short machine-readable string describing the first violation found.
    """
    if not isinstance(payload, dict):
        return False, "payload_not_a_dict"

    # Resolve claims list (support both "claims" and "candidates" keys)
    claims = payload.get("claims")
    if not isinstance(claims, list):
        claims = payload.get("candidates")
    if not isinstance(claims, list):
        return False, "missing_claims_list"
    if len(claims) == 0:
        return True, "ok"

    for idx, entry in enumerate(claims):
        if not isinstance(entry, dict):
            return False, f"claim[{idx}]_not_a_dict"

        # Validate required string fields
        for field in _REQUIRED_STR_FIELDS:
            val = entry.get(field)
            if not isinstance(val, str) or not val.strip():
                return False, f"claim[{idx}]_missing_{field}"

        # Validate required integer span fields (support direct or evidence_span alias)
        evidence_span = entry.get("evidence_span")
        has_direct_span = isinstance(
            entry.get("support_char_start"), int
        ) and isinstance(entry.get("support_char_end"), int)
        has_alias_span = (
            isinstance(evidence_span, dict)
            and isinstance(evidence_span.get("char_start"), int)
            and isinstance(evidence_span.get("char_end"), int)
        )
        if not has_direct_span and not has_alias_span:
            # Provide field-specific error when one direct field is present
            if isinstance(entry.get("support_char_start"), int):
                return False, f"claim[{idx}]_missing_support_char_end"
            return False, f"claim[{idx}]_missing_support_char_start"

        if has_direct_span:
            char_start = entry["support_char_start"]
            char_end = entry["support_char_end"]
        else:
            char_start = evidence_span["char_start"]
            char_end = evidence_span["char_end"]
        if char_start < 0:
            return False, f"claim[{idx}]_support_char_start_negative"
        if char_end <= char_start:
            return False, f"claim[{idx}]_zero_length_span"

        # Validate optional token span coherence (both or neither)
        has_token_start = "support_token_start" in entry
        has_token_end = "support_token_end" in entry
        if has_token_start != has_token_end:
            return False, f"claim[{idx}]_partial_token_span"
        if has_token_start:
            ts = entry["support_token_start"]
            te = entry["support_token_end"]
            if not isinstance(ts, int) or not isinstance(te, int):
                return False, f"claim[{idx}]_token_span_not_int"
            if ts < 0 or te <= ts:
                return False, f"claim[{idx}]_invalid_token_span_range"

        # Validate optional float fields range
        for field in _OPTIONAL_FLOAT_FIELDS:
            if field not in entry:
                continue
            val = entry[field]
            if not isinstance(val, (int, float)):
                return False, f"claim[{idx}]_{field}_not_numeric"
            if not (0.0 <= float(val) <= 1.0):
                return False, f"claim[{idx}]_{field}_out_of_range"

        # Validate optional support_quote_text type
        sqt = entry.get("support_quote_text")
        if sqt is not None and not isinstance(sqt, str):
            return False, f"claim[{idx}]_support_quote_text_not_str"

        # Validate optional metadata type
        meta = entry.get("metadata")
        if meta is not None and not isinstance(meta, dict):
            return False, f"claim[{idx}]_metadata_not_dict"

        # Validate optional evidence_kind / evidence_relation values.
        # evidence_relation is kept as a compatibility alias for older payloads.
        ev_kind = entry.get("evidence_kind")
        if ev_kind is not None:
            if not isinstance(ev_kind, str) or ev_kind not in _VALID_EVIDENCE_KINDS:
                return False, f"claim[{idx}]_evidence_kind_invalid"

        ev_rel = entry.get("evidence_relation")
        if ev_rel is not None:
            if not isinstance(ev_rel, str) or not ev_rel.strip():
                return False, f"claim[{idx}]_evidence_relation_invalid"
            if ev_kind is None and ev_rel in _VALID_EVIDENCE_KINDS:
                pass

        support_relation = entry.get("support_relation")
        if support_relation is not None:
            if (
                not isinstance(support_relation, str)
                or support_relation not in _VALID_SUPPORT_RELATIONS
            ):
                return False, f"claim[{idx}]_support_relation_invalid"

        # Validate quote aligns with source_text when provided
        if source_text is not None:
            if char_end > len(source_text):
                return False, f"claim[{idx}]_span_out_of_bounds"
            sqt = entry.get("support_quote_text")
            if sqt is not None and isinstance(sqt, str):
                if not validate_span(source_text, char_start, char_end, sqt):
                    return False, f"claim[{idx}]_quote_mismatch"

    return True, "ok"
