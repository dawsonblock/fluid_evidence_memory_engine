from __future__ import annotations

from pathlib import Path
from typing import Any

from feme.claim_extractor import extract_candidates_for_evidence
from feme.db import Database
from feme.evidence import EvidenceIngestor
from feme.extractors.registry import ExtractorRegistry

TEXT = "FEME must use PostgreSQL as canonical memory."


class FakeStructuredProvider:
    name = "fake_llm_span"
    version = "test"

    def __init__(self, responses: list[Any]):
        self._responses = list(responses)

    def extract(self, _chunk_text: str, _metadata: dict[str, Any]) -> Any:
        if not self._responses:
            return {"claims": []}
        return self._responses.pop(0)


def _db(tmp_path: Path) -> Database:
    db = Database(str(tmp_path / "mocked-span-llm.sqlite"))
    db.init()
    return db


def _ingest(db: Database, text: str = TEXT) -> str:
    return EvidenceIngestor(db).ingest_text(text, source_type="official_record")["evidence_id"]


def _registry(provider: FakeStructuredProvider) -> ExtractorRegistry:
    registry = ExtractorRegistry()
    registry.register(provider)
    return registry


def test_valid_json_correct_span_is_accepted(tmp_path: Path):
    db = _db(tmp_path)
    evidence_id = _ingest(db)
    provider = FakeStructuredProvider(
        [
            {
                "claims": [
                    {
                        "subject": "FEME",
                        "predicate": "must_use",
                        "object": "PostgreSQL as canonical memory",
                        "claim_text": TEXT,
                        "support_char_start": 0,
                        "support_char_end": len(TEXT),
                        "support_quote_text": TEXT,
                    }
                ]
            }
        ]
    )
    candidates = extract_candidates_for_evidence(
        db,
        evidence_id,
        extractor_mode="json_strict",
        extractor_provider=provider.name,
        provider_registry=_registry(provider),
    )
    assert len(candidates) == 1


def test_wrong_offset_can_be_repaired_when_policy_enabled(tmp_path: Path):
    db = _db(tmp_path)
    evidence_id = _ingest(db)
    provider = FakeStructuredProvider(
        [
            {
                "claims": [
                    {
                        "subject": "FEME",
                        "predicate": "must_use",
                        "object": "PostgreSQL as canonical memory",
                        "claim_text": TEXT,
                        "support_char_start": 1,
                        "support_char_end": len(TEXT),
                        "support_quote_text": TEXT,
                    }
                ]
            }
        ]
    )
    candidates = extract_candidates_for_evidence(
        db,
        evidence_id,
        extractor_mode="json_strict",
        extractor_provider=provider.name,
        extractor_config={"allow_deterministic_span_repair": True},
        provider_registry=_registry(provider),
    )
    assert len(candidates) == 1
    assert candidates[0].support_char_start == 0


def test_quote_mismatch_rejected_in_strict_mode(tmp_path: Path):
    db = _db(tmp_path)
    evidence_id = _ingest(db)
    provider = FakeStructuredProvider(
        [
            {
                "claims": [
                    {
                        "subject": "FEME",
                        "predicate": "must_use",
                        "object": "PostgreSQL as canonical memory",
                        "claim_text": TEXT,
                        "support_char_start": 0,
                        "support_char_end": len(TEXT),
                        "support_quote_text": "wrong",
                    }
                ]
            }
        ]
    )
    candidates = extract_candidates_for_evidence(
        db,
        evidence_id,
        extractor_mode="json_strict",
        extractor_provider=provider.name,
        provider_registry=_registry(provider),
    )
    assert candidates == []


def test_out_of_bounds_span_rejected(tmp_path: Path):
    db = _db(tmp_path)
    evidence_id = _ingest(db)
    provider = FakeStructuredProvider(
        [
            {
                "claims": [
                    {
                        "subject": "FEME",
                        "predicate": "must_use",
                        "object": "PostgreSQL as canonical memory",
                        "claim_text": TEXT,
                        "support_char_start": 0,
                        "support_char_end": 999,
                        "support_quote_text": TEXT,
                    }
                ]
            }
        ]
    )
    candidates = extract_candidates_for_evidence(
        db,
        evidence_id,
        extractor_mode="json_strict",
        extractor_provider=provider.name,
        provider_registry=_registry(provider),
    )
    assert candidates == []


def test_empty_claims_is_valid_zero_claim_result(tmp_path: Path):
    db = _db(tmp_path)
    evidence_id = _ingest(db)
    provider = FakeStructuredProvider([{"claims": []}])
    candidates = extract_candidates_for_evidence(
        db,
        evidence_id,
        extractor_mode="json_strict",
        extractor_provider=provider.name,
        provider_registry=_registry(provider),
    )
    assert candidates == []


def test_malformed_json_repair_failure_in_strict_returns_zero(tmp_path: Path):
    db = _db(tmp_path)
    evidence_id = _ingest(db)
    provider = FakeStructuredProvider(["{broken", "still not json", "also bad"])
    candidates = extract_candidates_for_evidence(
        db,
        evidence_id,
        extractor_mode="json_strict",
        extractor_provider=provider.name,
        provider_registry=_registry(provider),
    )
    assert candidates == []
