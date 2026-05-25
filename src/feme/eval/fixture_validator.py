from __future__ import annotations

from pathlib import Path
from typing import Any

from ..spans import validate_span
from ..utils import json_loads

_VALID_SUPPORT_RELATIONS = {
    "supports",
    "contradicts",
    "summarizes",
    "mentions",
    "inferred_from",
    "unknown",
}

_VALID_EVIDENCE_KINDS = {"direct", "inference", "summary", "unknown"}


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
        row_number = idx + 1
        raw_case_id = row.get("case_id")
        case_id = str(raw_case_id or "").strip() or f"row_{row_number}"

        if not isinstance(raw_case_id, str) or not str(raw_case_id).strip():
            errors.append(
                {
                    "row": row_number,
                    "case_id": case_id,
                    "reason": "missing_case_id",
                }
            )

        raw_text = row.get("text")
        text = str(raw_text or "")
        if not isinstance(raw_text, str) or not raw_text:
            errors.append(
                {
                    "row": row_number,
                    "case_id": case_id,
                    "reason": "missing_text",
                }
            )

        if case_id in seen_case_ids:
            errors.append(
                {
                    "row": row_number,
                    "case_id": case_id,
                    "reason": "duplicate_case_id",
                }
            )
        seen_case_ids.add(case_id)

        if "expected_claims" not in row:
            errors.append(
                {
                    "row": row_number,
                    "case_id": case_id,
                    "reason": "missing_expected_claims",
                }
            )
            continue

        expected_claims = row.get("expected_claims")
        if not isinstance(expected_claims, list):
            errors.append(
                {
                    "row": row_number,
                    "case_id": case_id,
                    "reason": "expected_claims_not_list",
                }
            )
            continue

        for claim_idx, claim in enumerate(expected_claims):
            if not isinstance(claim, dict):
                errors.append(
                    {
                        "row": row_number,
                        "case_id": case_id,
                        "claim_index": claim_idx,
                        "reason": "expected_claim_not_dict",
                    }
                )
                continue

            claim_text = claim.get("claim_text")
            if not isinstance(claim_text, str) or not claim_text.strip():
                errors.append(
                    {
                        "row": row_number,
                        "case_id": case_id,
                        "claim_index": claim_idx,
                        "reason": "missing_claim_text",
                    }
                )

            start = claim.get("char_start")
            end = claim.get("char_end")
            quote = claim.get("support_quote_text")

            if not isinstance(start, int) or not isinstance(end, int):
                errors.append(
                    {
                        "row": row_number,
                        "case_id": case_id,
                        "claim_index": claim_idx,
                        "reason": "missing_or_invalid_char_bounds",
                    }
                )
                continue

            if start < 0 or end <= start or end > len(text):
                errors.append(
                    {
                        "row": row_number,
                        "case_id": case_id,
                        "claim_index": claim_idx,
                        "reason": "char_bounds_out_of_range",
                        "char_start": start,
                        "char_end": end,
                        "text_length": len(text),
                    }
                )
                continue

            if not isinstance(quote, str) or not quote:
                errors.append(
                    {
                        "row": row_number,
                        "case_id": case_id,
                        "claim_index": claim_idx,
                        "reason": "missing_support_quote_text",
                    }
                )
                continue

            if not validate_span(text, start, end, quote):
                errors.append(
                    {
                        "row": row_number,
                        "case_id": case_id,
                        "claim_index": claim_idx,
                        "reason": "expected_quote_span_mismatch",
                        "char_start": start,
                        "char_end": end,
                        "expected_quote": quote,
                        "actual_slice": text[start:end],
                    }
                )

            support_relation = claim.get("support_relation")
            if support_relation is not None and support_relation not in _VALID_SUPPORT_RELATIONS:
                errors.append(
                    {
                        "row": row_number,
                        "case_id": case_id,
                        "claim_index": claim_idx,
                        "reason": "invalid_support_relation",
                        "support_relation": support_relation,
                    }
                )

            evidence_kind = claim.get("evidence_kind")
            if evidence_kind is not None and evidence_kind not in _VALID_EVIDENCE_KINDS:
                errors.append(
                    {
                        "row": row_number,
                        "case_id": case_id,
                        "claim_index": claim_idx,
                        "reason": "invalid_evidence_kind",
                        "evidence_kind": evidence_kind,
                    }
                )

    return {
        "fixture_path": fixture_path,
        "case_count": len(rows),
        "valid": len(errors) == 0,
        "error_count": len(errors),
        "errors": errors,
    }
