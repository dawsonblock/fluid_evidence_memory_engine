from __future__ import annotations

from pathlib import Path
from typing import Any

from feme.claim_extractor import extract_candidates_for_evidence
from feme.db import Database
from feme.evidence import EvidenceIngestor
from feme.extractors.registry import ExtractorRegistry

TEXT = "FEME must use PostgreSQL as canonical memory."


class FakeStructuredProvider:
    name = "fake_quality_modes"
    version = "test"

    def __init__(self, responses: list[Any]):
        self._responses = list(responses)
        self.calls = 0

    def extract(self, _chunk_text: str, _metadata: dict[str, Any]) -> Any:
        self.calls += 1
        if not self._responses:
            return {"claims": []}
        value = self._responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def _db(tmp_path: Path) -> Database:
    db = Database(str(tmp_path / "strict-quality.sqlite"))
    db.init()
    return db


def _ingest(db: Database, text: str = TEXT) -> str:
    return EvidenceIngestor(db).ingest_text(text, source_type="official_record")["evidence_id"]


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


def test_json_strict_valid_provider_writes_claims(tmp_path: Path):
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
    assert _latest_audit(db, evidence_id)["outcome"] == "structured_success"


def test_json_strict_malformed_output_writes_zero_after_repair_failure(tmp_path: Path):
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
    assert _latest_audit(db, evidence_id)["outcome"] == "strict_rejected"


def test_json_strict_quote_mismatch_writes_zero_claims(tmp_path: Path):
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
    assert _latest_audit(db, evidence_id)["outcome"] == "strict_rejected"


def test_json_strict_empty_claims_records_structured_success(tmp_path: Path):
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
    assert int(audit["candidate_count"]) == 0


def test_json_with_fallback_malformed_output_falls_back_to_heuristic(tmp_path: Path):
    db = _db(tmp_path)
    evidence_id = _ingest(db)
    provider = FakeStructuredProvider(["{broken", "still not json", "also bad"])
    candidates = extract_candidates_for_evidence(
        db,
        evidence_id,
        extractor_mode="json_with_fallback",
        extractor_provider=provider.name,
        provider_registry=_registry(provider),
    )
    assert len(candidates) >= 1
    assert _latest_audit(db, evidence_id)["outcome"] == "heuristic_fallback"


def test_heuristic_mode_ignores_structured_provider(tmp_path: Path):
    db = _db(tmp_path)
    evidence_id = _ingest(db)
    provider = FakeStructuredProvider([RuntimeError("should not be called")])
    candidates = extract_candidates_for_evidence(
        db,
        evidence_id,
        extractor_mode="heuristic",
        extractor_provider=provider.name,
        provider_registry=_registry(provider),
    )
    assert len(candidates) >= 1
    assert provider.calls == 0
    assert _latest_audit(db, evidence_id)["outcome"] == "heuristic_success"
