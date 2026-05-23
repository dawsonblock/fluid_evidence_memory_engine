from pathlib import Path

from feme.claim_extractor import (
    extract_candidates_for_evidence,
    extract_candidates_from_chunk,
)
from feme.db import Database
from feme.evidence import EvidenceIngestor


def _db(tmp_path: Path) -> Database:
    db = Database(str(tmp_path / "json-adapter.sqlite"))
    db.init()
    return db


def test_json_adapter_produces_structured_candidate_with_strict_span(tmp_path: Path):
    chunk = {
        "id": "ch_1",
        "evidence_id": "ev_1",
        "text": "Memory engine must use PostgreSQL as canonical database.",
        "chunk_index": 0,
        "char_start": 0,
        "token_start": 0,
        "source_quality": 0.95,
        "source_type": "official_record",
        "review_required": 0,
        "span_id": None,
    }

    def _json_extractor(_text: str, _chunk: dict) -> dict:
        return {
            "candidates": [
                {
                    "subject": "Memory engine",
                    "predicate": "must_use",
                    "object": "PostgreSQL",
                    "claim_text": "Memory engine must use PostgreSQL as canonical database.",
                    "support_char_start": 0,
                    "support_char_end": 54,
                }
            ]
        }

    candidates = extract_candidates_from_chunk(
        chunk,
        json_claim_extractor=_json_extractor,
    )
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.subject == "Memory engine"
    assert candidate.predicate == "must_use"
    assert candidate.object == "PostgreSQL"
    assert candidate.metadata["extractor"] == "json-adapter-v1"
    assert candidate.support_char_start == 0
    assert candidate.support_char_end == 54


def test_json_adapter_accepts_claims_key_alias(tmp_path: Path):
    chunk = {
        "id": "ch_1",
        "evidence_id": "ev_1",
        "text": "Memory engine must use PostgreSQL as canonical database.",
        "chunk_index": 0,
        "char_start": 0,
        "token_start": 0,
        "source_quality": 0.95,
        "source_type": "official_record",
        "review_required": 0,
        "span_id": None,
    }

    def _json_extractor(_text: str, _chunk: dict) -> dict:
        return {
            "claims": [
                {
                    "subject": "Memory engine",
                    "predicate": "must_use",
                    "object": "PostgreSQL",
                    "claim_text": "Memory engine must use PostgreSQL as canonical database.",
                    "support_char_start": 0,
                    "support_char_end": 54,
                }
            ]
        }

    candidates = extract_candidates_from_chunk(
        chunk,
        json_claim_extractor=_json_extractor,
    )
    assert len(candidates) == 1
    assert candidates[0].metadata["extractor"] == "json-adapter-v1"


def test_json_adapter_accepts_evidence_span_alias(tmp_path: Path):
    chunk = {
        "id": "ch_1",
        "evidence_id": "ev_1",
        "text": "Memory engine must use PostgreSQL as canonical database.",
        "chunk_index": 0,
        "char_start": 0,
        "token_start": 0,
        "source_quality": 0.95,
        "source_type": "official_record",
        "review_required": 0,
        "span_id": None,
    }

    def _json_extractor(_text: str, _chunk: dict) -> dict:
        return {
            "claims": [
                {
                    "subject": "Memory engine",
                    "predicate": "must_use",
                    "object": "PostgreSQL",
                    "claim_text": "Memory engine must use PostgreSQL as canonical database.",
                    "evidence_span": {
                        "char_start": 0,
                        "char_end": 54,
                    },
                }
            ]
        }

    candidates = extract_candidates_from_chunk(
        chunk,
        json_claim_extractor=_json_extractor,
    )
    assert len(candidates) == 1
    assert candidates[0].metadata["extractor"] == "json-adapter-v1"


def test_json_adapter_quote_mismatch_falls_back_to_heuristic(tmp_path: Path):
    chunk = {
        "id": "ch_1",
        "evidence_id": "ev_1",
        "text": "Memory engine must use PostgreSQL as canonical database.",
        "chunk_index": 0,
        "char_start": 0,
        "token_start": 0,
        "source_quality": 0.95,
        "source_type": "official_record",
        "review_required": 0,
        "span_id": None,
    }

    def _json_extractor(_text: str, _chunk: dict) -> dict:
        return {
            "candidates": [
                {
                    "subject": "Memory engine",
                    "predicate": "must_use",
                    "object": "PostgreSQL",
                    "claim_text": "Memory engine must use PostgreSQL as canonical database.",
                    "support_char_start": 0,
                    "support_char_end": 13,
                    "support_quote_text": "This does not match",
                }
            ]
        }

    candidates = extract_candidates_from_chunk(
        chunk,
        json_claim_extractor=_json_extractor,
    )
    assert candidates
    assert any(c.metadata.get("extractor") == "heuristic-v2" for c in candidates)


def test_json_adapter_quote_mismatch_strict_mode_fails_closed(tmp_path: Path):
    chunk = {
        "id": "ch_1",
        "evidence_id": "ev_1",
        "text": "Memory engine must use PostgreSQL as canonical database.",
        "chunk_index": 0,
        "char_start": 0,
        "token_start": 0,
        "source_quality": 0.95,
        "source_type": "official_record",
        "review_required": 0,
        "span_id": None,
    }

    def _json_extractor(_text: str, _chunk: dict) -> dict:
        return {
            "candidates": [
                {
                    "subject": "Memory engine",
                    "predicate": "must_use",
                    "object": "PostgreSQL",
                    "claim_text": "Memory engine must use PostgreSQL as canonical database.",
                    "support_char_start": 0,
                    "support_char_end": 13,
                    "support_quote_text": "This does not match",
                }
            ]
        }

    candidates = extract_candidates_from_chunk(
        chunk,
        json_claim_extractor=_json_extractor,
        extractor_mode="json_strict",
    )
    assert candidates == []


def test_json_adapter_zero_length_token_span_falls_back_to_heuristic(tmp_path: Path):
    chunk = {
        "id": "ch_1",
        "evidence_id": "ev_1",
        "text": "Memory engine must use PostgreSQL as canonical database.",
        "chunk_index": 0,
        "char_start": 0,
        "token_start": 0,
        "source_quality": 0.95,
        "source_type": "official_record",
        "review_required": 0,
        "span_id": None,
    }

    def _json_extractor(_text: str, _chunk: dict) -> dict:
        return {
            "candidates": [
                {
                    "subject": "Memory engine",
                    "predicate": "must_use",
                    "object": "PostgreSQL",
                    "claim_text": "Memory engine must use PostgreSQL as canonical database.",
                    "support_char_start": 0,
                    "support_char_end": 13,
                    "support_token_start": 2,
                    "support_token_end": 2,
                }
            ]
        }

    candidates = extract_candidates_from_chunk(
        chunk,
        json_claim_extractor=_json_extractor,
    )
    assert candidates
    assert any(c.metadata.get("extractor") == "heuristic-v2" for c in candidates)


def test_json_adapter_invalid_payload_falls_back_to_heuristic(tmp_path: Path):
    chunk = {
        "id": "ch_1",
        "evidence_id": "ev_1",
        "text": "Memory engine must use PostgreSQL as canonical database.",
        "chunk_index": 0,
        "char_start": 0,
        "token_start": 0,
        "source_quality": 0.95,
        "source_type": "official_record",
        "review_required": 0,
        "span_id": None,
    }

    def _bad_json_extractor(_text: str, _chunk: dict) -> dict:
        return {
            "candidates": [
                {
                    "subject": "Memory engine",
                    # Missing required fields and invalid span.
                    "support_char_start": 99,
                    "support_char_end": 1,
                }
            ]
        }

    candidates = extract_candidates_from_chunk(
        chunk,
        json_claim_extractor=_bad_json_extractor,
    )
    assert candidates
    assert any(c.metadata.get("extractor") == "heuristic-v2" for c in candidates)


def test_json_adapter_works_in_extract_for_evidence(tmp_path: Path):
    db = _db(tmp_path)
    evidence = EvidenceIngestor(db).ingest_text(
        "Claims must link to exact evidence spans.",
        source_type="official_record",
    )

    def _json_extractor(_text: str, _chunk: dict) -> dict:
        # The ingested chunk text for this test starts with this sentence.
        return {
            "candidates": [
                {
                    "subject": "Claims",
                    "predicate": "must_link_to",
                    "object": "exact evidence spans",
                    "claim_text": "Claims must link to exact evidence spans.",
                    "support_char_start": 0,
                    "support_char_end": 40,
                }
            ]
        }

    candidates = extract_candidates_for_evidence(
        db,
        evidence["evidence_id"],
        json_claim_extractor=_json_extractor,
    )
    assert candidates
    assert candidates[0].metadata["extractor"] == "json-adapter-v1"
