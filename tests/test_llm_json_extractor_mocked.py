from __future__ import annotations

from pathlib import Path
from typing import Any

from feme.claim_extractor import extract_candidates_for_evidence
from feme.db import Database
from feme.evidence import EvidenceIngestor
from feme.extractors.registry import ExtractorRegistry


TEXT = "FEME must use PostgreSQL as canonical memory."


class FakeStructuredProvider:
    name = "fake_llm"
    version = "test"

    def __init__(self, responses: list[Any]):
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def extract(self, chunk_text: str, metadata: dict[str, Any]) -> Any:
        self.calls.append({"chunk_text": chunk_text, "metadata": dict(metadata)})
        if not self._responses:
            return {"claims": []}
        return self._responses.pop(0)


def _db(tmp_path: Path) -> Database:
    db = Database(str(tmp_path / "mocked-llm.sqlite"))
    db.init()
    return db


def _ingest(db: Database, text: str = TEXT) -> str:
    result = EvidenceIngestor(db).ingest_text(text, source_type="official_record")
    return result["evidence_id"]


def _registry(provider: FakeStructuredProvider) -> ExtractorRegistry:
    registry = ExtractorRegistry()
    registry.register(provider)
    return registry


def _latest_audit(db: Database, evidence_id: str):
    with db.connect() as con:
        return con.execute(
            """
            SELECT outcome, detail, candidate_count
            FROM extractor_audit
            WHERE evidence_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (evidence_id,),
        ).fetchone()


def test_valid_json_produces_candidates(tmp_path: Path):
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
    assert candidates[0].support_quote_text == TEXT


def test_malformed_json_triggers_repair_and_succeeds(tmp_path: Path):
    db = _db(tmp_path)
    evidence_id = _ingest(db)
    provider = FakeStructuredProvider(
        [
            "{broken",
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
            },
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
    assert len(provider.calls) == 2
    assert provider.calls[1]["metadata"]["is_repair_attempt"] is True


def test_repair_failure_in_json_strict_returns_zero_candidates(tmp_path: Path):
    db = _db(tmp_path)
    evidence_id = _ingest(db)
    provider = FakeStructuredProvider(
        ["{broken", "still not json", "also not json"]
    )

    candidates = extract_candidates_for_evidence(
        db,
        evidence_id,
        extractor_mode="json_strict",
        extractor_provider=provider.name,
        provider_registry=_registry(provider),
    )

    assert candidates == []
    audit = _latest_audit(db, evidence_id)
    assert audit["outcome"] == "strict_rejected"


def test_quote_mismatch_is_rejected(tmp_path: Path):
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
                        "support_quote_text": "wrong quote",
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
    audit = _latest_audit(db, evidence_id)
    assert audit["outcome"] == "strict_rejected"


def test_empty_claims_list_is_valid(tmp_path: Path):
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
    audit = _latest_audit(db, evidence_id)
    assert audit["outcome"] == "structured_success"
    assert audit["candidate_count"] == 0
