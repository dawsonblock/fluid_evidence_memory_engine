from __future__ import annotations

from pathlib import Path
from typing import Any

from feme.claim_extractor import extract_candidates_for_evidence
from feme.db import Database
from feme.evidence import EvidenceIngestor
from feme.extractors.registry import ExtractorRegistry

TEXT = "FEME must use PostgreSQL as canonical memory."


class FakeStructuredProvider:
    name = "fake_llm_quality"
    version = "test"

    def __init__(self, responses: list[Any]):
        self._responses = list(responses)

    def extract(self, _chunk_text: str, _metadata: dict[str, Any]) -> Any:
        if not self._responses:
            return {"claims": []}
        return self._responses.pop(0)


def _db(tmp_path: Path) -> Database:
    db = Database(str(tmp_path / "mocked-llm-quality.sqlite"))
    db.init()
    return db


def _ingest(db: Database, text: str = TEXT) -> str:
    return EvidenceIngestor(db).ingest_text(text, source_type="official_record")["evidence_id"]


def _registry(provider: FakeStructuredProvider) -> ExtractorRegistry:
    registry = ExtractorRegistry()
    registry.register(provider)
    return registry


def _latest_outcome(db: Database, evidence_id: str) -> str:
    with db.connect() as con:
        row = con.execute(
            """
            SELECT outcome
            FROM extractor_audit
            WHERE evidence_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (evidence_id,),
        ).fetchone()
    return str(row["outcome"])


def test_valid_single_claim_json(tmp_path: Path):
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
                        "evidence_kind": "direct",
                        "support_relation": "supports",
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


def test_valid_multi_claim_json(tmp_path: Path):
    db = _db(tmp_path)
    text = "FEME uses PostgreSQL. FEME links claims to spans."
    evidence_id = _ingest(db, text=text)
    provider = FakeStructuredProvider(
        [
            {
                "claims": [
                    {
                        "subject": "FEME",
                        "predicate": "uses",
                        "object": "PostgreSQL",
                        "claim_text": "FEME uses PostgreSQL.",
                        "support_char_start": 0,
                        "support_char_end": 21,
                        "support_quote_text": "FEME uses PostgreSQL.",
                    },
                    {
                        "subject": "FEME",
                        "predicate": "links",
                        "object": "claims to spans",
                        "claim_text": "FEME links claims to spans.",
                        "support_char_start": 22,
                        "support_char_end": 49,
                        "support_quote_text": "FEME links claims to spans.",
                    },
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
    assert len(candidates) == 2


def test_empty_claims_list(tmp_path: Path):
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
    assert _latest_outcome(db, evidence_id) == "structured_success"


def test_malformed_json_repaired_successfully(tmp_path: Path):
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


def test_malformed_json_repair_failure(tmp_path: Path):
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
    assert _latest_outcome(db, evidence_id) == "strict_rejected"


def test_wrong_span_repaired_from_quote(tmp_path: Path):
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


def test_quote_mismatch_rejected(tmp_path: Path):
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


def test_evidence_kind_labels_and_contradiction_relation_preserved(tmp_path: Path):
    db = _db(tmp_path)
    text = "FEME uses PostgreSQL. This contradicts the previous SQLite-only claim."
    evidence_id = _ingest(db, text=text)
    provider = FakeStructuredProvider(
        [
            {
                "claims": [
                    {
                        "subject": "FEME",
                        "predicate": "uses",
                        "object": "PostgreSQL",
                        "claim_text": "FEME uses PostgreSQL.",
                        "support_char_start": 0,
                        "support_char_end": 21,
                        "support_quote_text": "FEME uses PostgreSQL.",
                        "evidence_kind": "direct",
                        "support_relation": "supports",
                    },
                    {
                        "subject": "This",
                        "predicate": "contradicts",
                        "object": "the previous SQLite-only claim",
                        "claim_text": "This contradicts the previous SQLite-only claim.",
                        "support_char_start": 22,
                            "support_char_end": 70,
                        "support_quote_text": "This contradicts the previous SQLite-only claim.",
                        "evidence_kind": "inference",
                        "support_relation": "contradicts",
                    },
                    {
                        "subject": "status",
                        "predicate": "is",
                        "object": "stable",
                        "claim_text": "status is stable",
                        "support_char_start": 0,
                        "support_char_end": 21,
                        "support_quote_text": "FEME uses PostgreSQL.",
                        "evidence_kind": "summary",
                        "support_relation": "summarizes",
                    },
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
    assert len(candidates) == 3
    assert candidates[0].evidence_kind == "direct"
    assert candidates[1].evidence_kind == "inference"
    assert candidates[2].evidence_kind == "summary"
    assert candidates[1].support_relation == "contradicts"
