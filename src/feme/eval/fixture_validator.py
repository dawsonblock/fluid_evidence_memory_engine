from __future__ import annotations

from pathlib import Path
from typing import Any

from ..spans import validate_span
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


def validate_extraction_fixture_file(fixture_path: str) -> dict[str, Any]:
    rows = _read_jsonl(Path(fixture_path))
    errors: list[dict[str, Any]] = []
    seen_case_ids: set[str] = set()

    for idx, row in enumerate(rows):
        case_id = str(row.get("case_id") or f"line_{idx + 1}")
        text = str(row.get("text") or "")

        if case_id in seen_case_ids:
            errors.append({"case_id": case_id, "reason": "duplicate_case_id"})
        seen_case_ids.add(case_id)

        expected_claims = row.get("expected_claims")
        if expected_claims is None:
            expected_claims = []
        if not isinstance(expected_claims, list):
            errors.append({"case_id": case_id, "reason": "expected_claims_not_list"})
            continue

        for claim_idx, claim in enumerate(expected_claims):
            if not isinstance(claim, dict):
                errors.append(
                    {
                        "case_id": case_id,
                        "claim_index": claim_idx,
                        "reason": "expected_claim_not_dict",
                    }
                )
                continue

            start = claim.get("char_start")
            end = claim.get("char_end")
            quote = claim.get("support_quote_text")

            if not isinstance(start, int) or not isinstance(end, int):
                errors.append(
                    {
                        "case_id": case_id,
                        "claim_index": claim_idx,
                        "reason": "missing_or_invalid_char_bounds",
                    }
                )
                continue

            if start < 0 or end <= start or end > len(text):
                errors.append(
                    {
                        "case_id": case_id,
                        "claim_index": claim_idx,
                        "reason": "char_bounds_out_of_range",
                        "char_start": start,
                        "char_end": end,
                        "text_length": len(text),
                    }
                )
                continue

            if isinstance(quote, str):
                if not validate_span(text, start, end, quote):
                    errors.append(
                        {
                            "case_id": case_id,
                            "claim_index": claim_idx,
                            "reason": "expected_quote_span_mismatch",
                            "char_start": start,
                            "char_end": end,
                            "expected_quote": quote,
                            "actual_slice": text[start:end],
                        }
                    )

    return {
        "fixture_path": fixture_path,
        "case_count": len(rows),
        "valid": len(errors) == 0,
        "error_count": len(errors),
        "errors": errors,
    }
