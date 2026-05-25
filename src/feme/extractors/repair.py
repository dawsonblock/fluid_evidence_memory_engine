"""JSON repair helper for FEME extractor pipeline.

When a structured extractor returns malformed JSON, ``attempt_repair`` tries
to recover a valid claim-extraction-v1 payload by asking the same extractor
to re-extract from a minimal prompt that includes the broken output.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from ..spans import find_exact_quote_span, validate_span

if TYPE_CHECKING:
    from feme.extractors.base import ExtractorProvider


def attempt_repair(
    bad_json_str: str,
    extractor: "ExtractorProvider",
    max_attempts: int = 2,
) -> "dict[str, Any] | None":
    """Try to repair *bad_json_str* using *extractor*.

    Parameters
    ----------
    bad_json_str:
        The raw (possibly truncated or malformed) string that could not be
        parsed as valid claim-extraction-v1 JSON.
    extractor:
        An :class:`~feme.extractors.base.ExtractorProvider` whose ``extract``
        method will be called with a repair prompt.
    max_attempts:
        Maximum number of repair attempts before giving up.

    Returns
    -------
    dict | None
        A parsed dict when repair succeeds, or ``None`` on failure.
    """
    # Fast path: maybe it just needs whitespace trimming or a code-fence strip
    cleaned = _strip_code_fence(bad_json_str.strip())
    result = _try_parse(cleaned)
    if result is not None:
        return result

    for _attempt in range(max_attempts):
        # Build a repair prompt embedding the broken output
        repair_prompt = (
            "The following JSON output is malformed. "
            "Fix it so it is valid claim-extraction-v1 JSON "
            "(a dict with a 'claims' list). "
            "Return ONLY the corrected JSON, no explanation.\n\n"
            f"Broken output:\n{bad_json_str}"
        )
        try:
            repaired = extractor.extract(
                repair_prompt,
                {"extractor_mode": "repair", "is_repair_attempt": True},
            )
        except Exception:  # noqa: BLE001
            continue

        if isinstance(repaired, dict) and (
            "claims" in repaired or "candidates" in repaired
        ):
            return repaired

        # extractor may have returned the raw string inside a wrapper
        content = repaired.get("content") if isinstance(repaired, dict) else None
        if isinstance(content, str):
            result = _try_parse(_strip_code_fence(content.strip()))
            if result is not None:
                return result

    return None


def repair_payload_span_offsets(
    payload: dict[str, Any],
    *,
    source_text: str,
    require_unique_quote: bool,
) -> tuple[dict[str, Any], bool, str | None]:
    """Deterministically repair support char offsets from support_quote_text.

    Returns `(payload, repaired_any, error_reason)` where `error_reason` is set
    only when a repair was required but could not be performed deterministically.
    """
    claims = payload.get("claims")
    claims_key = "claims"
    if not isinstance(claims, list):
        claims = payload.get("candidates")
        claims_key = "candidates"
    if not isinstance(claims, list):
        return payload, False, None

    repaired_any = False
    for idx, claim in enumerate(claims):
        if not isinstance(claim, dict):
            continue
        quote = claim.get("support_quote_text")
        start = claim.get("support_char_start")
        end = claim.get("support_char_end")

        if not isinstance(quote, str) or not quote:
            continue
        if not isinstance(start, int) or not isinstance(end, int):
            continue
        if validate_span(source_text, start, end, quote):
            continue

        quote_count = source_text.count(quote)
        if require_unique_quote and quote_count == 0:
            return payload, repaired_any, f"claim[{idx}]_span_repair_failed"
        if require_unique_quote and quote_count > 1:
            return payload, repaired_any, f"claim[{idx}]_span_repair_ambiguous"

        match = find_exact_quote_span(source_text, quote, occurrence_index=0)
        if match is None:
            return payload, repaired_any, f"claim[{idx}]_span_repair_failed"

        claim["support_char_start"] = match.char_start
        claim["support_char_end"] = match.char_end
        evidence_span = claim.get("evidence_span")
        if isinstance(evidence_span, dict):
            evidence_span["char_start"] = match.char_start
            evidence_span["char_end"] = match.char_end
        repaired_any = True

    payload[claims_key] = claims
    return payload, repaired_any, None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _strip_code_fence(text: str) -> str:
    """Remove ```json ... ``` fences if present."""
    pattern = r"^```(?:json)?\s*(.*?)\s*```$"
    match = re.match(pattern, text, re.DOTALL)
    if match:
        return match.group(1)
    return text


def _try_parse(text: str) -> "dict[str, Any] | None":
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    if "claims" in parsed or "candidates" in parsed:
        return parsed
    return None
