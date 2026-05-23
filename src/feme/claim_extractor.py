from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any, Literal, Union

from .db import Database
from .models import ClaimCandidate, MemoryLevel, MemoryType
from .policy import MemoryPolicy
from .token_trace import Tokenizer
from .utils import json_dumps, new_id, now_iso

EXPLICIT_MARKERS = [
    "remember",
    "from now on",
    "going forward",
    "use ",
    "make sure",
    "we decided",
    "actually",
    "correction",
    "must",
]

PROJECT_MARKERS = [
    "postgres",
    "pgvector",
    "qdrant",
    "memory",
    "database",
    "evidence",
    "claim",
    "schema",
    "repo",
    "api",
    "module",
    "engine",
    "token",
    "span",
    "retrieval",
]

INFERENCE_MARKERS = [
    "maybe",
    "could",
    "infer",
    "suggests",
    "appears",
    "probably",
    "likely",
]
CORRECTION_MARKERS = [
    "actually",
    "correction",
    "instead",
    "replace",
    "supersede",
    "not anymore",
]

JsonClaimExtractor = Callable[
    [str, dict[str, Any]],
    Union[dict[str, Any], list[dict[str, Any]]],
]
ExtractorMode = Literal["heuristic", "json_with_fallback", "json_strict"]


def extract_candidates_from_chunk(
    chunk: dict,
    policy: MemoryPolicy | None = None,
    *,
    json_claim_extractor: JsonClaimExtractor | None = None,
    extractor_mode: str = "json_with_fallback",
    extractor_provider: str | None = None,
) -> list[ClaimCandidate]:
    candidates, _, _ = _extract_candidates_with_status(
        chunk,
        policy=policy,
        json_claim_extractor=json_claim_extractor,
        extractor_mode=extractor_mode,
        extractor_provider=extractor_provider,
    )
    return candidates


def _extract_candidates_with_status(
    chunk: dict,
    policy: MemoryPolicy | None = None,
    *,
    json_claim_extractor: JsonClaimExtractor | None = None,
    extractor_mode: str = "json_with_fallback",
    extractor_provider: str | None = None,
) -> tuple[list[ClaimCandidate], str, str | None]:
    policy = policy or MemoryPolicy.default()
    text = str(chunk.get("text") or "")
    provider_label = _resolve_provider_label(extractor_provider, extractor_mode)
    if not text:
        return [], "structured_empty", "chunk_text_empty"

    if extractor_mode not in {"heuristic", "json_with_fallback", "json_strict"}:
        extractor_mode = "json_with_fallback"

    if extractor_mode != "heuristic" and json_claim_extractor is not None:
        try:
            payload = json_claim_extractor(text, dict(chunk))
            structured = _structured_candidates_from_json(
                payload,
                dict(chunk),
                policy,
                extractor_provider=provider_label,
            )
            if structured:
                return structured, "structured_success", None
            if extractor_mode == "json_strict":
                return [], "strict_rejected", "structured_empty"
        except Exception as exc:
            if extractor_mode == "json_strict":
                return [], "strict_rejected", f"structured_error:{exc.__class__.__name__}"
            # Structured extraction is optional; fall back to deterministic heuristics.
            heuristic = _heuristic_candidates(
                text,
                chunk,
                policy,
                extractor_provider=provider_label,
            )
            return (
                heuristic,
                "heuristic_fallback",
                f"structured_error:{exc.__class__.__name__}",
            )

        heuristic = _heuristic_candidates(
            text,
            chunk,
            policy,
            extractor_provider=provider_label,
        )
        return heuristic, "heuristic_fallback", "structured_empty"

    heuristic = _heuristic_candidates(
        text,
        chunk,
        policy,
        extractor_provider=provider_label,
    )
    if extractor_mode == "heuristic":
        return heuristic, "heuristic_success", None
    return heuristic, "heuristic_fallback", "structured_extractor_unavailable"


def _heuristic_candidates(
    text: str,
    chunk: dict,
    policy: MemoryPolicy,
    *,
    extractor_provider: str,
) -> list[ClaimCandidate]:
    sentences = _sentence_spans(text)
    tokenized = Tokenizer().tokenize(text)
    out: list[ClaimCandidate] = []
    for sentence, char_start, char_end in sentences:
        token_start, token_end = _token_range_for_char_span(
            tokenized,
            char_start,
            char_end,
        )
        candidate = _sentence_to_candidate(
            sentence,
            chunk,
            policy,
            support_char_start=char_start,
            support_char_end=char_end,
            support_token_start=token_start,
            support_token_end=token_end,
            extractor_provider=extractor_provider,
        )
        if candidate:
            out.append(candidate)
    return out


def extract_candidates_for_evidence(
    db: Database,
    evidence_id: str,
    policy: MemoryPolicy | None = None,
    json_claim_extractor: JsonClaimExtractor | None = None,
    extractor_mode: str = "json_with_fallback",
    extractor_provider: str | None = None,
    *,
    con=None,
) -> list[ClaimCandidate]:
    if con is None:
        with db.connect() as con2:
            rows = con2.execute(
                """
                SELECT
                    tc.*,
                    ts.id AS span_id,
                    es.source_type,
                    es.project_id,
                    sr.review_required
                FROM text_chunks tc
                LEFT JOIN token_spans ts ON ts.chunk_id = tc.id
                LEFT JOIN evidence_sources es ON es.id = tc.evidence_id
                LEFT JOIN source_registry sr
                  ON sr.project_id = es.project_id AND sr.source_type = es.source_type
                WHERE tc.evidence_id = ?
                ORDER BY tc.chunk_index
                """,
                (evidence_id,),
            ).fetchall()
    else:
        rows = con.execute(
            """
            SELECT
                tc.*,
                ts.id AS span_id,
                es.source_type,
                es.project_id,
                sr.review_required
            FROM text_chunks tc
            LEFT JOIN token_spans ts ON ts.chunk_id = tc.id
            LEFT JOIN evidence_sources es ON es.id = tc.evidence_id
            LEFT JOIN source_registry sr
              ON sr.project_id = es.project_id AND sr.source_type = es.source_type
            WHERE tc.evidence_id = ?
            ORDER BY tc.chunk_index
            """,
            (evidence_id,),
        ).fetchall()
    candidates: list[ClaimCandidate] = []
    for row in rows:
        chunk = dict(row)
        chunk_candidates, outcome, detail = _extract_candidates_with_status(
            chunk,
            policy=policy,
            json_claim_extractor=json_claim_extractor,
            extractor_mode=extractor_mode,
            extractor_provider=extractor_provider,
        )
        _persist_extractor_audit(
            db,
            chunk=chunk,
            extractor_mode=extractor_mode,
            extractor_provider=_resolve_provider_label(
                extractor_provider,
                extractor_mode,
            ),
            outcome=outcome,
            candidate_count=len(chunk_candidates),
            detail=detail,
            con=con,
        )
        candidates.extend(chunk_candidates)
    return candidates


def _structured_candidates_from_json(
    payload: dict[str, Any] | list[dict[str, Any]],
    chunk: dict[str, Any],
    policy: MemoryPolicy,
    *,
    extractor_provider: str,
) -> list[ClaimCandidate]:
    entries = _normalize_json_candidates_payload(payload)
    if not entries:
        return []

    out: list[ClaimCandidate] = []
    chunk_text = str(chunk.get("text") or "")
    tokenized = Tokenizer().tokenize(chunk_text)

    for entry in entries:
        candidate = _candidate_from_structured_json(
            entry,
            chunk,
            chunk_text=chunk_text,
            tokenized=tokenized,
            policy=policy,
            extractor_provider=extractor_provider,
        )
        if candidate is not None:
            out.append(candidate)
    return out


def _normalize_json_candidates_payload(
    payload: dict[str, Any] | list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        candidates = payload.get("candidates")
        if not isinstance(candidates, list):
            candidates = payload.get("claims")
        if isinstance(candidates, list):
            return [item for item in candidates if isinstance(item, dict)]
    return []


def _candidate_from_structured_json(
    entry: dict[str, Any],
    chunk: dict[str, Any],
    *,
    chunk_text: str,
    tokenized,
    policy: MemoryPolicy,
    extractor_provider: str,
) -> ClaimCandidate | None:
    subject = _required_str(entry, "subject")
    predicate = _required_str(entry, "predicate")
    obj = _required_str(entry, "object")
    claim_text = _required_str(entry, "claim_text")
    if not (subject and predicate and obj and claim_text):
        return None

    char_start, char_end = _read_char_span(entry, chunk_text)
    if char_start is None or char_end is None:
        return None

    has_token_span = "support_token_start" in entry or "support_token_end" in entry
    token_start, token_end = _read_token_span(entry)
    if has_token_span and (token_start is None or token_end is None):
        return None
    if token_start is None or token_end is None:
        token_start, token_end = _token_range_for_char_span(
            tokenized,
            char_start,
            char_end,
        )

    chunk_char_start = int(chunk.get("char_start") or 0)
    support_char_start_abs = chunk_char_start + char_start
    support_char_end_abs = chunk_char_start + char_end
    chunk_token_start = int(chunk.get("token_start") or 0)
    support_token_start_abs = (
        chunk_token_start + token_start if token_start is not None else None
    )
    support_token_end_abs = (
        chunk_token_start + token_end if token_end is not None else None
    )

    source_quality = float(chunk.get("source_quality", 0.5))
    quoted_span = chunk_text[char_start:char_end]
    provided_quote = entry.get("support_quote_text")
    if provided_quote is not None:
        if not isinstance(provided_quote, str):
            return None
        if provided_quote != quoted_span:
            return None
        quote_text = provided_quote
    else:
        quote_text = quoted_span
    memory_type = _parse_memory_type(entry.get("memory_type"))
    metadata = dict(entry.get("metadata") or {})
    metadata.update(
        {
            "extractor": "json-adapter-v1",
            "extractor_provider": extractor_provider,
            "structured_json": True,
            "chunk_index": chunk.get("chunk_index"),
            "source_type": chunk.get("source_type"),
            "source_review_required": bool(chunk.get("review_required", 0)),
            "support_char_start": support_char_start_abs,
            "support_char_end": support_char_end_abs,
            "support_token_start": support_token_start_abs,
            "support_token_end": support_token_end_abs,
            "support_quote_text": quote_text,
        }
    )

    return ClaimCandidate(
        subject=subject[:240],
        predicate=predicate[:120],
        object=obj[:500],
        claim_text=claim_text,
        memory_type=memory_type,
        memory_level=MemoryLevel.project_memory,
        confidence=_float_or_default(entry.get("confidence"), 0.64),
        salience=_float_or_default(entry.get("salience"), 0.68),
        source_quality=source_quality,
        user_explicitness=_float_or_default(entry.get("user_explicitness"), 0.9),
        long_term_usefulness=_float_or_default(entry.get("long_term_usefulness"), 0.78),
        project_relevance=_float_or_default(entry.get("project_relevance"), 0.9),
        actionability=_float_or_default(entry.get("actionability"), 0.72),
        contradiction_value=_float_or_default(entry.get("contradiction_value"), 0.0),
        privacy_sensitivity=policy.privacy_sensitivity_for_text(claim_text),
        uncertainty=_float_or_default(entry.get("uncertainty"), 0.18),
        triviality=_float_or_default(entry.get("triviality"), 0.05),
        short_livedness=_float_or_default(entry.get("short_livedness"), 0.05),
        evidence_id=chunk.get("evidence_id"),
        chunk_id=chunk.get("id"),
        span_id=chunk.get("span_id"),
        support_char_start=support_char_start_abs,
        support_char_end=support_char_end_abs,
        support_token_start=support_token_start_abs,
        support_token_end=support_token_end_abs,
        support_quote_text=quote_text,
        metadata=metadata,
    )


def _required_str(entry: dict[str, Any], key: str) -> str | None:
    value = entry.get(key)
    if not isinstance(value, str):
        return None
    clean = value.strip()
    return clean or None


def _read_char_span(
    entry: dict[str, Any],
    chunk_text: str,
) -> tuple[int | None, int | None]:
    start_raw = entry.get("support_char_start")
    end_raw = entry.get("support_char_end")
    if not isinstance(start_raw, int) or not isinstance(end_raw, int):
        evidence_span = entry.get("evidence_span")
        if isinstance(evidence_span, dict):
            start_raw = evidence_span.get("char_start")
            end_raw = evidence_span.get("char_end")
    if not isinstance(start_raw, int) or not isinstance(end_raw, int):
        return None, None
    if start_raw < 0 or end_raw <= start_raw or end_raw > len(chunk_text):
        return None, None
    return start_raw, end_raw


def _read_token_span(entry: dict[str, Any]) -> tuple[int | None, int | None]:
    start_raw = entry.get("support_token_start")
    end_raw = entry.get("support_token_end")
    if not isinstance(start_raw, int) or not isinstance(end_raw, int):
        return None, None
    if start_raw < 0 or end_raw <= start_raw:
        return None, None
    return start_raw, end_raw


def _parse_memory_type(value: Any) -> MemoryType:
    if isinstance(value, str):
        try:
            return MemoryType(value)
        except ValueError:
            return MemoryType.unknown
    return MemoryType.project_decision


def _float_or_default(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _sentence_spans(text: str) -> list[tuple[str, int, int]]:
    spans: list[tuple[str, int, int]] = []
    start = 0
    for match in re.finditer(r"(?<=[.!?])\s+|\n+", text):
        end = match.start()
        sentence = text[start:end].strip()
        if len(sentence) >= 12:
            left_trimmed = len(text[start:end]) - len(text[start:end].lstrip())
            right_trimmed = len(text[start:end].rstrip())
            absolute_start = start + left_trimmed
            absolute_end = start + right_trimmed
            spans.append((sentence, absolute_start, absolute_end))
        start = match.end()
    tail = text[start:]
    sentence = tail.strip()
    if len(sentence) >= 12:
        left_trimmed = len(tail) - len(tail.lstrip())
        right_trimmed = len(tail.rstrip())
        absolute_start = start + left_trimmed
        absolute_end = start + right_trimmed
        spans.append((sentence, absolute_start, absolute_end))
    return spans


def _sentence_to_candidate(
    sentence: str,
    chunk: dict,
    policy: MemoryPolicy,
    *,
    support_char_start: int | None = None,
    support_char_end: int | None = None,
    support_token_start: int | None = None,
    support_token_end: int | None = None,
    extractor_provider: str = "heuristic",
) -> ClaimCandidate | None:
    lowered = sentence.lower()
    explicitness = 1.0 if any(m in lowered for m in EXPLICIT_MARKERS) else 0.2
    project_relevance = 0.9 if any(m in lowered for m in PROJECT_MARKERS) else 0.4

    patterns = [
        (r"use\s+(.+?)\s+as\s+(.+)", "uses_as"),
        (r"(.+?)\s+should\s+use\s+(.+)", "should_use"),
        (r"(.+?)\s+must\s+use\s+(.+)", "must_use"),
        (r"(.+?)\s+is\s+not\s+(.+)", "is_not"),
        (r"(.+?)\s+is\s+(.+)", "is"),
        (r"(.+?)\s+stores?\s+(.+)", "stores"),
        (r"(.+?)\s+links?\s+(.+)", "links"),
        (r"(.+?)\s+contradicts?\s+(.+)", "contradicts"),
        (r"(.+?)\s+replaces?\s+(.+)", "replaces"),
    ]
    subject = None
    predicate = "states"
    obj = sentence
    for pattern, pred in patterns:
        match = re.match(pattern, sentence, flags=re.IGNORECASE)
        if match:
            groups = match.groups()
            if pred == "uses_as":
                subject = groups[0].strip()
                obj = groups[1].strip()
            else:
                subject = groups[0].strip()
                obj = groups[1].strip()
            predicate = pred
            break
    if subject is None:
        if project_relevance < 0.7 and explicitness < 0.7:
            return None
        subject = _guess_subject(sentence)
        predicate = "states"
        obj = sentence

    memory_type = (
        MemoryType.project_decision
        if project_relevance >= 0.7
        else MemoryType.evidence_claim
    )
    if any(m in lowered for m in INFERENCE_MARKERS):
        memory_type = MemoryType.inference
    if any(m in lowered for m in CORRECTION_MARKERS):
        memory_type = MemoryType.correction

    source_quality = float(chunk.get("source_quality", 0.5))
    privacy_sensitivity = policy.privacy_sensitivity_for_text(sentence)
    chunk_char_start = int(chunk.get("char_start") or 0)
    support_char_start_abs = (
        chunk_char_start + support_char_start
        if support_char_start is not None
        else None
    )
    support_char_end_abs = (
        chunk_char_start + support_char_end if support_char_end is not None else None
    )
    chunk_token_start = int(chunk.get("token_start") or 0)
    support_token_start_abs = (
        chunk_token_start + support_token_start
        if support_token_start is not None
        else None
    )
    support_token_end_abs = (
        chunk_token_start + support_token_end if support_token_end is not None else None
    )

    return ClaimCandidate(
        subject=subject[:240],
        predicate=predicate[:120],
        object=obj[:500],
        claim_text=sentence,
        memory_type=memory_type,
        memory_level=MemoryLevel.project_memory,
        confidence=(
            0.64
            if memory_type not in {MemoryType.inference, MemoryType.correction}
            else 0.50
        ),
        salience=0.68 if project_relevance >= 0.7 else 0.45,
        source_quality=source_quality,
        user_explicitness=explicitness,
        long_term_usefulness=0.78 if project_relevance >= 0.7 else 0.45,
        project_relevance=project_relevance,
        actionability=(
            0.72
            if any(
                v in lowered
                for v in ["use", "must", "should", "store", "build", "replace"]
            )
            else 0.4
        ),
        contradiction_value=0.65 if memory_type == MemoryType.correction else 0.0,
        privacy_sensitivity=privacy_sensitivity,
        uncertainty=0.45 if memory_type == MemoryType.inference else 0.18,
        triviality=0.05 if project_relevance >= 0.7 else 0.25,
        short_livedness=0.05 if project_relevance >= 0.7 else 0.25,
        evidence_id=chunk.get("evidence_id"),
        chunk_id=chunk.get("id"),
        span_id=chunk.get("span_id"),
        support_char_start=support_char_start_abs,
        support_char_end=support_char_end_abs,
        support_token_start=support_token_start_abs,
        support_token_end=support_token_end_abs,
        support_quote_text=sentence,
        metadata={
            "extractor": "heuristic-v2",
            "extractor_provider": extractor_provider,
            "chunk_index": chunk.get("chunk_index"),
            "source_type": chunk.get("source_type"),
            "source_review_required": bool(chunk.get("review_required", 0)),
            "support_char_start": support_char_start_abs,
            "support_char_end": support_char_end_abs,
            "support_token_start": support_token_start_abs,
            "support_token_end": support_token_end_abs,
            "support_quote_text": sentence,
        },
    )


def _guess_subject(sentence: str) -> str:
    words = sentence.split()
    return " ".join(words[: min(6, len(words))])


def _resolve_provider_label(
    extractor_provider: str | None,
    extractor_mode: str,
) -> str:
    if isinstance(extractor_provider, str) and extractor_provider.strip():
        return extractor_provider.strip()
    if extractor_mode == "heuristic":
        return "heuristic"
    return "structured"


def _persist_extractor_audit(
    db: Database,
    *,
    chunk: dict[str, Any],
    extractor_mode: str,
    extractor_provider: str,
    outcome: str,
    candidate_count: int,
    detail: str | None,
    con=None,
) -> None:
    metadata = {
        "chunk_index": chunk.get("chunk_index"),
        "source_type": chunk.get("source_type"),
        "review_required": bool(chunk.get("review_required", 0)),
    }
    params = (
        new_id("exaudit"),
        chunk.get("project_id") or "default",
        chunk.get("evidence_id"),
        chunk.get("id"),
        extractor_mode,
        extractor_provider,
        outcome,
        candidate_count,
        detail or "",
        json_dumps(metadata),
        now_iso(),
    )
    sql = """
        INSERT INTO extractor_audit (
            id,
            project_id,
            evidence_id,
            chunk_id,
            extractor_mode,
            extractor_provider,
            outcome,
            candidate_count,
            detail,
            metadata_json,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    try:
        if con is not None:
            con.execute(sql, params)
            return
        with db.connect() as con2:
            con2.execute(sql, params)
            con2.commit()
    except Exception:
        # Extraction must remain available even if audit persistence is unavailable.
        return


def _token_range_for_char_span(
    tokens,
    char_start: int,
    char_end: int,
) -> tuple[int | None, int | None]:
    token_indexes = [
        token.token_index
        for token in tokens
        if token.char_end > char_start and token.char_start < char_end
    ]
    if not token_indexes:
        return None, None
    return min(token_indexes), max(token_indexes) + 1
