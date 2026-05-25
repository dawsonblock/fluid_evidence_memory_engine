from __future__ import annotations

from pathlib import Path
from typing import Any

from ..claim_extractor import extract_candidates_from_chunk
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


def _normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().lower().split())


def _expected_claims(row: dict[str, Any]) -> list[dict[str, Any]]:
    claims = row.get("expected_claims")
    if isinstance(claims, list):
        return [c for c in claims if isinstance(c, dict)]
    claims = row.get("claims")
    if isinstance(claims, list):
        return [c for c in claims if isinstance(c, dict)]
    return []


def _expected_count_bounds(
    row: dict[str, Any],
    expected_claims: list[dict[str, Any]],
) -> tuple[int, int]:
    lower = row.get("expected_claim_count_min")
    upper = row.get("expected_claim_count_max")
    default_count = len(expected_claims)
    if not isinstance(lower, int):
        lower = default_count
    if not isinstance(upper, int):
        upper = default_count
    lower = max(0, lower)
    upper = max(lower, upper)
    return lower, upper


def _candidate_to_dict(candidate: Any) -> dict[str, Any]:
    return {
        "claim_text": candidate.claim_text,
        "support_quote_text": candidate.support_quote_text,
        "char_start": candidate.support_char_start,
        "char_end": candidate.support_char_end,
        "subject": candidate.subject,
        "predicate": candidate.predicate,
        "object": candidate.object,
        "support_relation": candidate.support_relation,
        "evidence_kind": candidate.evidence_kind,
    }


def _claim_match_score(expected: dict[str, Any], actual: Any) -> int:
    expected_claim_text = _normalize_text(expected.get("claim_text"))
    expected_quote = _normalize_text(expected.get("support_quote_text"))
    actual_claim_text = _normalize_text(getattr(actual, "claim_text", None))
    actual_quote = _normalize_text(getattr(actual, "support_quote_text", None))

    score = 0
    if expected_claim_text and expected_claim_text == actual_claim_text:
        score += 3
    if expected_quote and expected_quote == actual_quote:
        score += 2

    expected_subject = _normalize_text(expected.get("subject"))
    expected_predicate = _normalize_text(expected.get("predicate"))
    expected_object = _normalize_text(expected.get("object"))
    if expected_subject and expected_subject == _normalize_text(getattr(actual, "subject", None)):
        score += 1
    if expected_predicate and expected_predicate == _normalize_text(getattr(actual, "predicate", None)):
        score += 1
    if expected_object and expected_object == _normalize_text(getattr(actual, "object", None)):
        score += 1
    return score


def _match_claims(
    expected_claims: list[dict[str, Any]],
    actual_claims: list[Any],
) -> tuple[list[tuple[dict[str, Any], Any]], list[dict[str, Any]], list[Any]]:
    matched: list[tuple[dict[str, Any], Any]] = []
    used_actual_indexes: set[int] = set()

    for expected in expected_claims:
        best_index = None
        best_score = 0
        for idx, actual in enumerate(actual_claims):
            if idx in used_actual_indexes:
                continue
            score = _claim_match_score(expected, actual)
            if score > best_score:
                best_score = score
                best_index = idx
        if best_index is not None and best_score > 0:
            used_actual_indexes.add(best_index)
            matched.append((expected, actual_claims[best_index]))

    missed = [
        expected
        for expected in expected_claims
        if all(expected is not m[0] for m in matched)
    ]
    false_positives = [
        actual
        for idx, actual in enumerate(actual_claims)
        if idx not in used_actual_indexes
    ]
    return matched, missed, false_positives


def _span_debug_reason(
    expected_start: Any,
    expected_end: Any,
    expected_quote: Any,
    actual_start: Any,
    actual_end: Any,
    actual_quote: Any,
    source_text: str,
) -> str:
    if actual_quote != expected_quote and actual_start == expected_start and actual_end == expected_end:
        return "quote_mismatch"
    if actual_start != expected_start or actual_end != expected_end:
        if (
            isinstance(actual_start, int)
            and isinstance(actual_end, int)
            and isinstance(actual_quote, str)
            and not validate_span(source_text, actual_start, actual_end, actual_quote)
        ):
            return "offset_mismatch_and_invalid_slice"
        return "offset_mismatch"
    if (
        isinstance(actual_start, int)
        and isinstance(actual_end, int)
        and isinstance(actual_quote, str)
        and not validate_span(source_text, actual_start, actual_end, actual_quote)
    ):
        return "span_invalid"
    return "none"


def evaluate_extraction_fixture(
    fixture_path: str,
    *,
    extractor_mode: str = "heuristic",
    extractor_provider: str | None = None,
    verbose: bool = False,
    debug: bool = False,
    debug_spans: bool = False,
) -> dict[str, Any]:
    rows = _read_jsonl(Path(fixture_path))
    if not rows:
        result = {
            "fixture_path": fixture_path,
            "case_count": 0,
            "claim_count_accuracy": 0.0,
            "multi_claim_count_accuracy": 0.0,
            "support_span_exact_match": 0.0,
            "support_quote_exact_match": 0.0,
            "support_span_validity_rate": 0.0,
            "quote_exact_match": 0.0,
            "false_positive_rate": 0.0,
            "false_negative_rate": 0.0,
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "evidence_kind_accuracy": 0.0,
            "direct_kind_accuracy": 0.0,
            "inference_kind_accuracy": 0.0,
            "summary_kind_accuracy": 0.0,
            "support_relation_accuracy": 0.0,
            "invalid_output_rejection": 0.0,
            "fallback_rate": 0.0,
            "strict_rejection_rate": 0.0,
            "extractor_mode": extractor_mode,
            "extractor_provider": extractor_provider,
        }
        if verbose or debug:
            result["cases"] = []
        if debug_spans:
            result["span_debug"] = []
        return result

    case_count = len(rows)
    claim_count_ok = 0
    multi_claim_case_count = 0
    multi_claim_count_ok = 0

    total_expected = 0
    total_predicted = 0
    total_matched = 0
    total_false_negatives = 0

    span_expected_count = 0
    span_match_ok = 0
    quote_match_ok = 0

    span_valid_total = 0
    span_valid_ok = 0

    empty_expected_cases = 0
    empty_expected_cases_with_fp = 0

    kind_expected = {"direct": 0, "inference": 0, "summary": 0}
    kind_correct = {"direct": 0, "inference": 0, "summary": 0}
    kind_overall_expected = 0
    kind_overall_correct = 0

    relation_expected = 0
    relation_correct = 0

    invalid_rejection_ok = 0
    fallback_count = 0
    strict_rejections = 0

    cases: list[dict[str, Any]] = []
    span_debug: list[dict[str, Any]] = []

    for idx, row in enumerate(rows):
        case_id = str(row.get("case_id") or f"case_{idx + 1}")
        text = str(row.get("text") or "")
        expected = _expected_claims(row)
        min_count, max_count = _expected_count_bounds(row, expected)
        expect_strict_rejection = bool(row.get("expect_strict_rejection", False))
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
                p: dict[str, Any] | None = structured_payload,
            ) -> dict[str, Any]:
                return p or {}

            json_extractor = _json_extractor

        actual_claims = extract_candidates_from_chunk(
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
            if extractor_mode == "json_strict" and not actual_claims:
                invalid_rejection_ok += 1
                strict_rejections += 1
            if verbose or debug:
                cases.append(
                    {
                        "case_id": case_id,
                        "source_text": text,
                        "expected_claims": expected,
                        "actual_claims": [_candidate_to_dict(c) for c in actual_claims],
                        "misses": [],
                        "false_positives": [],
                        "span_errors": [],
                        "miss_reason": (
                            None if not actual_claims else "expected_strict_rejection"
                        ),
                    }
                )
            continue

        predicted_count = len(actual_claims)
        total_predicted += predicted_count
        if min_count <= predicted_count <= max_count:
            claim_count_ok += 1

        if len(expected) > 1:
            multi_claim_case_count += 1
            if predicted_count == len(expected):
                multi_claim_count_ok += 1

        if not expected:
            empty_expected_cases += 1
            if predicted_count > 0:
                empty_expected_cases_with_fp += 1

        total_expected += len(expected)
        matched, misses, false_positives = _match_claims(expected, actual_claims)
        total_matched += len(matched)
        total_false_negatives += len(misses)

        for expected_claim, actual in matched:
            expected_start = expected_claim.get("char_start")
            expected_end = expected_claim.get("char_end")
            expected_quote = expected_claim.get("support_quote_text")
            actual_start = actual.support_char_start
            actual_end = actual.support_char_end
            actual_quote = actual.support_quote_text

            if isinstance(expected_start, int) and isinstance(expected_end, int):
                span_expected_count += 1
                if actual_start == expected_start and actual_end == expected_end:
                    span_match_ok += 1
            if isinstance(expected_quote, str):
                if actual_quote == expected_quote:
                    quote_match_ok += 1

            expected_kind = expected_claim.get("evidence_kind")
            actual_kind = actual.evidence_kind
            if isinstance(expected_kind, str) and expected_kind:
                kind_overall_expected += 1
                if actual_kind == expected_kind:
                    kind_overall_correct += 1
                if expected_kind in kind_expected:
                    kind_expected[expected_kind] += 1
                    if actual_kind == expected_kind:
                        kind_correct[expected_kind] += 1

            expected_relation = expected_claim.get("support_relation")
            if isinstance(expected_relation, str) and expected_relation:
                relation_expected += 1
                if actual.support_relation == expected_relation:
                    relation_correct += 1

            if debug_spans and (
                actual_start != expected_start
                or actual_end != expected_end
                or actual_quote != expected_quote
            ):
                expected_slice = (
                    text[expected_start:expected_end]
                    if isinstance(expected_start, int) and isinstance(expected_end, int)
                    else None
                )
                actual_slice = (
                    text[actual_start:actual_end]
                    if isinstance(actual_start, int) and isinstance(actual_end, int)
                    else None
                )
                span_debug.append(
                    {
                        "case_id": case_id,
                        "source_text": text,
                        "expected": {
                            "quote": expected_quote,
                            "char_start": expected_start,
                            "char_end": expected_end,
                            "source_slice": expected_slice,
                        },
                        "actual": {
                            "quote": actual_quote,
                            "char_start": actual_start,
                            "char_end": actual_end,
                            "source_slice": actual_slice,
                        },
                        "span_exact": (
                            actual_start == expected_start and actual_end == expected_end
                        ),
                        "quote_exact": actual_quote == expected_quote,
                        "reason": _span_debug_reason(
                            expected_start,
                            expected_end,
                            expected_quote,
                            actual_start,
                            actual_end,
                            actual_quote,
                            text,
                        ),
                    }
                )

        for actual in actual_claims:
            start = actual.support_char_start
            end = actual.support_char_end
            quote = actual.support_quote_text
            if isinstance(start, int) and isinstance(end, int) and isinstance(quote, str):
                span_valid_total += 1
                if validate_span(text, start, end, quote):
                    span_valid_ok += 1

        if actual_claims and any(
            (c.metadata or {}).get("extractor") == "heuristic-v2" for c in actual_claims
        ):
            fallback_count += 1

        if verbose or debug:
            span_errors = []
            for expected_claim, actual in matched:
                expected_start = expected_claim.get("char_start")
                expected_end = expected_claim.get("char_end")
                expected_quote = expected_claim.get("support_quote_text")
                actual_start = actual.support_char_start
                actual_end = actual.support_char_end
                actual_quote = actual.support_quote_text
                if (
                    actual_start != expected_start
                    or actual_end != expected_end
                    or actual_quote != expected_quote
                ):
                    span_errors.append(
                        {
                            "expected_quote": expected_quote,
                            "actual_quote": actual_quote,
                            "expected_start": expected_start,
                            "actual_start": actual_start,
                            "expected_end": expected_end,
                            "actual_end": actual_end,
                        }
                    )

            cases.append(
                {
                    "case_id": case_id,
                    "source_text": text,
                    "expected_claims": expected,
                    "actual_claims": [_candidate_to_dict(c) for c in actual_claims],
                    "misses": [
                        {
                            "type": "missing_claim",
                            "expected_claim_text": miss.get("claim_text"),
                        }
                        for miss in misses
                    ],
                    "false_positives": [
                        {
                            "claim_text": fp.claim_text,
                            "reason": "not_matched_to_expected",
                        }
                        for fp in false_positives
                    ],
                    "span_errors": span_errors,
                    "miss_reason": None if not misses else "missing_claims",
                }
            )

    precision = (
        total_matched / total_predicted
        if total_predicted > 0
        else (1.0 if total_expected == 0 else 0.0)
    )
    recall = total_matched / total_expected if total_expected > 0 else 1.0
    f1 = (
        (2.0 * precision * recall / (precision + recall))
        if (precision + recall) > 0
        else 0.0
    )

    result = {
        "fixture_path": fixture_path,
        "case_count": case_count,
        "claim_count_accuracy": claim_count_ok / case_count,
        "multi_claim_count_accuracy": (
            multi_claim_count_ok / multi_claim_case_count
            if multi_claim_case_count > 0
            else 0.0
        ),
        "support_span_exact_match": (
            span_match_ok / span_expected_count if span_expected_count > 0 else 0.0
        ),
        "support_quote_exact_match": (
            quote_match_ok / span_expected_count if span_expected_count > 0 else 0.0
        ),
        "support_span_validity_rate": (
            span_valid_ok / span_valid_total if span_valid_total > 0 else 1.0
        ),
        "quote_exact_match": (
            quote_match_ok / span_expected_count if span_expected_count > 0 else 0.0
        ),
        "false_positive_rate": (
            empty_expected_cases_with_fp / empty_expected_cases
            if empty_expected_cases > 0
            else 0.0
        ),
        "false_negative_rate": (
            total_false_negatives / total_expected if total_expected > 0 else 0.0
        ),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "evidence_kind_accuracy": (
            kind_overall_correct / kind_overall_expected
            if kind_overall_expected > 0
            else 0.0
        ),
        "direct_kind_accuracy": (
            kind_correct["direct"] / kind_expected["direct"]
            if kind_expected["direct"] > 0
            else 0.0
        ),
        "inference_kind_accuracy": (
            kind_correct["inference"] / kind_expected["inference"]
            if kind_expected["inference"] > 0
            else 0.0
        ),
        "summary_kind_accuracy": (
            kind_correct["summary"] / kind_expected["summary"]
            if kind_expected["summary"] > 0
            else 0.0
        ),
        "support_relation_accuracy": (
            relation_correct / relation_expected if relation_expected > 0 else 0.0
        ),
        "invalid_output_rejection": invalid_rejection_ok / case_count,
        "fallback_rate": fallback_count / case_count,
        "strict_rejection_rate": strict_rejections / case_count,
        "extractor_mode": extractor_mode,
        "extractor_provider": extractor_provider,
    }
    if verbose or debug:
        result["cases"] = cases
    if debug_spans:
        result["span_debug"] = span_debug
    return result
