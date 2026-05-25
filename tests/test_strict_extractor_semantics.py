"""Regression guard for strict extractor fail-closed semantics (v0.7.6+).

These tests assert the externally visible contract:
  - json_strict with no provider: zero claims written, audit records strict_rejected
  - json_with_fallback with no provider: falls back to heuristic, claims written
  - heuristic mode: always writes claims
  - json_strict with invalid quote: zero claims written
"""

from pathlib import Path

from feme.claim_extractor import extract_candidates_for_evidence
from feme.db import Database
from feme.evidence import EvidenceIngestor
from feme.write_governor import MemoryWriteGovernor

_TEXT = "FEME must use PostgreSQL as canonical memory."


def _db(tmp_path: Path) -> Database:
    db = Database(str(tmp_path / "strict-semantics.sqlite"))
    db.init()
    return db


def _ingest(db: Database, text: str = _TEXT) -> str:
    result = EvidenceIngestor(db).ingest_text(text, source_type="official_record")
    return result["evidence_id"]


def _claim_count(db: Database) -> int:
    with db.connect() as con:
        row = con.execute("SELECT COUNT(*) AS n FROM memory_claims").fetchone()
    return int(row["n"])


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


def test_json_strict_without_provider_writes_no_claims(tmp_path: Path):
    db = _db(tmp_path)
    evidence_id = _ingest(db)
    candidates = extract_candidates_for_evidence(
        db,
        evidence_id,
        extractor_mode="json_strict",
        extractor_provider="missing-provider",
    )
    assert (
        candidates == []
    ), "json_strict with no provider must return empty candidate list"
    assert (
        _claim_count(db) == 0
    ), "json_strict with no provider must write zero memory_claims"


def test_json_strict_without_provider_records_strict_rejected(tmp_path: Path):
    db = _db(tmp_path)
    evidence_id = _ingest(db)
    extract_candidates_for_evidence(
        db,
        evidence_id,
        extractor_mode="json_strict",
        extractor_provider="missing-provider",
    )
    audit = _latest_audit(db, evidence_id)
    assert audit, "extractor_audit row must be written even on strict_rejected"
    assert audit["outcome"] == "strict_rejected"
    assert audit["detail"] == "structured_extractor_unavailable"


def test_json_with_fallback_without_provider_uses_heuristic(tmp_path: Path):
    db = _db(tmp_path)
    evidence_id = _ingest(db)
    candidates = extract_candidates_for_evidence(
        db,
        evidence_id,
        extractor_mode="json_with_fallback",
        extractor_provider="missing-provider",
    )
    assert (
        candidates
    ), "json_with_fallback must produce candidates via heuristic fallback"
    audit = _latest_audit(db, evidence_id)
    assert audit
    assert audit["outcome"] == "heuristic_fallback"
    assert audit["detail"] == "structured_extractor_unavailable"


def test_heuristic_mode_writes_heuristic_claims(tmp_path: Path):
    db = _db(tmp_path)
    evidence_id = _ingest(db)
    candidates = extract_candidates_for_evidence(
        db,
        evidence_id,
        extractor_mode="heuristic",
    )
    assert candidates, "heuristic mode must produce candidates"
    gov = MemoryWriteGovernor(db)
    for c in candidates:
        gov.commit_candidate(c, project_id="default")
    assert _claim_count(db) > 0, "heuristic mode must write claims to memory_claims"
    audit = _latest_audit(db, evidence_id)
    assert audit
    assert audit["outcome"] == "heuristic_success"


def test_json_strict_invalid_quote_writes_no_claims(tmp_path: Path):
    db = _db(tmp_path)
    evidence_id = _ingest(db)
    candidates = extract_candidates_for_evidence(
        db,
        evidence_id,
        extractor_mode="json_strict",
        extractor_provider="json_static",
        extractor_config={
            "claims": [
                {
                    "claim_text": _TEXT,
                    "subject": "FEME",
                    "predicate": "must_use",
                    "object": "PostgreSQL as canonical memory",
                    "support_char_start": 0,
                    "support_char_end": len(_TEXT),
                    "support_quote_text": "This is a deliberately wrong quote.",
                }
            ]
        },
    )
    assert (
        candidates == []
    ), "json_strict with quote mismatch must return empty candidate list"
    assert (
        _claim_count(db) == 0
    ), "json_strict with quote mismatch must write zero memory_claims"
    audit = _latest_audit(db, evidence_id)
    assert audit
    assert audit["outcome"] == "strict_rejected"
