from __future__ import annotations

from pathlib import Path
from typing import Any

from ..claim_extractor import extract_candidates_from_chunk
from ..utils import json_loads


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json_loads(line, default={})
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def evaluate_extraction_fixture(
    fixture_path: str,
    *,
    extractor_mode: str = "heuristic",
    extractor_provider: str | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    rows = _read_jsonl(Path(fixture_path))
    if not rows:
        result = {
            "fixture_path": fixture_path,
            "case_count": 0,
            "claim_count_accuracy": 0.0,
            "support_span_exact_match": 0.0,
            "quote_exact_match": 0.0,
            "invalid_output_rejection": 0.0,
            "fallback_rate": 0.0,
            "strict_rejection_rate": 0.0,
        }
        if verbose:
            result["cases"] = []
        return result

    claim_count_ok = 0
    span_match_ok = 0
    quote_match_ok = 0
    invalid_rejection_ok = 0
    fallback_count = 0
    strict_rejections = 0
    cases: list[dict[str, Any]] = []

    for idx, row in enumerate(rows):
        text = str(row.get("text") or "")
        expected_claims = row.get("expected_claims") or []
        expect_strict_rejection = bool(
            row.get("expect_strict_rejection", False)
        )
        structured_payload = row.get("structured_payload")

        chunk = {
            "id": f"chunk_{idx}",
            "evidence_id": f"ev_{idx}",
            "text": text,
            "chunk_index": 0,
            "char_start": 0,
            "token_start": 0,
            "source_quality": 0.95,
            "source_type": "official_record",
            "review_required": 0,
            "span_id": None,
        }

        json_extractor = None
        if isinstance(structured_payload, dict):
            def _json_extractor(
                _text: str,
                _chunk: dict[str, Any],
                p: dict[str, Any] = structured_payload,
            ) -> dict[str, Any]:
                return p

            json_extractor = _json_extractor

        candidates = extract_candidates_from_chunk(
            chunk,
            json_claim_extractor=json_extractor,
            extractor_mode=extractor_mode,
            extractor_provider=extractor_provider,
            extractor_config=(
                {"payload": structured_payload}
                if isinstance(structured_payload, dict)
                else None
            ),
        )

        if expect_strict_rejection:
            if extractor_mode == "json_strict" and not candidates:
                invalid_rejection_ok += 1
                strict_rejections += 1
            if verbose:
                cases.append(
                    {
                        "source_text": text,
                        "expected_claims": expected_claims,
                        "actual_claims": _serialize_candidates(candidates),
                        "expected_support_span": _first_expected_span(
                            expected_claims
                        ),
                        "actual_support_span": _first_actual_span(candidates),
                        "miss_reason": (
                            None if not candidates else "expected_strict_rejection"
                        ),
                    }
                )
            continue

        if len(candidates) == len(expected_claims):
            claim_count_ok += 1

        if candidates and expected_claims:
            c0 = candidates[0]
            e0 = expected_claims[0]
            expected_start = e0.get("char_start")
            expected_end = e0.get("char_end")
            if (
                c0.support_char_start == expected_start
                and c0.support_char_end == expected_end
            ):
                span_match_ok += 1
            if c0.support_quote_text == e0.get("support_quote_text"):
                quote_match_ok += 1

        if candidates and any(
            c.metadata.get("extractor") == "heuristic-v2" for c in candidates
        ):
            fallback_count += 1

        if verbose:
            cases.append(
                {
                    "source_text": text,
                    "expected_claims": expected_claims,
                    "actual_claims": _serialize_candidates(candidates),
                    "expected_support_span": _first_expected_span(
                        expected_claims
                    ),
                    "actual_support_span": _first_actual_span(candidates),
                    "miss_reason": _miss_reason(expected_claims, candidates),
                }
            )

    case_count = len(rows)
    result = {
        "fixture_path": fixture_path,
        "case_count": case_count,
        "claim_count_accuracy": claim_count_ok / case_count,
        "support_span_exact_match": span_match_ok / case_count,
        "quote_exact_match": quote_match_ok / case_count,
        "invalid_output_rejection": invalid_rejection_ok / case_count,
        "fallback_rate": fallback_count / case_count,
        "strict_rejection_rate": strict_rejections / case_count,
        "extractor_mode": extractor_mode,
        "extractor_provider": extractor_provider,
    }
    if verbose:
        result["cases"] = cases
    return result


def _serialize_candidates(candidates: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "claim_text": c.claim_text,
            "support_quote_text": c.support_quote_text,
            "char_start": c.support_char_start,
            "char_end": c.support_char_end,
        }
        for c in candidates
    ]


def _first_expected_span(
    expected_claims: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not expected_claims:
        return None
    first = expected_claims[0]
    return {
        "char_start": first.get("char_start"),
        "char_end": first.get("char_end"),
        "support_quote_text": first.get("support_quote_text"),
    }


def _first_actual_span(candidates: list[Any]) -> dict[str, Any] | None:
    if not candidates:
        return None
    first = candidates[0]
    return {
        "char_start": first.support_char_start,
        "char_end": first.support_char_end,
        "support_quote_text": first.support_quote_text,
    }


def _miss_reason(
    expected_claims: list[dict[str, Any]],
    candidates: list[Any],
) -> str | None:
    if len(candidates) != len(expected_claims):
        return "claim_count_mismatch"
    if not expected_claims and not candidates:
        return None
    if not candidates:
        return "no_candidates"

    expected = expected_claims[0]
    actual = candidates[0]
    if actual.support_char_start != expected.get("char_start"):
        return "support_char_start_mismatch"
    if actual.support_char_end != expected.get("char_end"):
        return "support_char_end_mismatch"
    if actual.support_quote_text != expected.get("support_quote_text"):
        return "support_quote_mismatch"
    return None
