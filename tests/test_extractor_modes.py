from pathlib import Path

from feme.claim_extractor import extract_candidates_for_evidence
from feme.db import Database
from feme.evidence import EvidenceIngestor
from feme.write_governor import MemoryWriteGovernor


def _db(tmp_path: Path) -> Database:
    db = Database(str(tmp_path / "extractor-modes.sqlite"))
    db.init()
    return db


def _ingest(db: Database, text: str) -> str:
    result = EvidenceIngestor(db).ingest_text(text, source_type="official_record")
    return result["evidence_id"]


def _claim_count(db: Database, evidence_id: str) -> int:
    with db.connect() as con:
        row = con.execute(
            "SELECT COUNT(*) AS n FROM claim_evidence_links WHERE evidence_id = ?",
            (evidence_id,),
        ).fetchone()
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


def test_json_strict_without_provider_fails_closed(tmp_path: Path):
    db = _db(tmp_path)
    evidence_id = _ingest(db, "FEME must use PostgreSQL as canonical memory.")

    candidates = extract_candidates_for_evidence(
        db,
        evidence_id,
        extractor_mode="json_strict",
        extractor_provider="missing-provider",
    )
    assert candidates == []
    assert _claim_count(db, evidence_id) == 0

    audit = _latest_audit(db, evidence_id)
    assert audit
    assert audit["outcome"] == "strict_rejected"
    assert audit["detail"] == "structured_extractor_unavailable"
    assert int(audit["candidate_count"]) == 0


def test_json_strict_invalid_output_writes_no_claims(tmp_path: Path):
    db = _db(tmp_path)
    evidence_id = _ingest(db, "FEME must use PostgreSQL as canonical memory.")

    candidates = extract_candidates_for_evidence(
        db,
        evidence_id,
        extractor_mode="json_strict",
        extractor_provider="json_static",
        extractor_config={
            "claims": [
                {
                    "subject": "FEME",
                    "predicate": "must_use",
                }
            ]
        },
    )
    assert candidates == []
    assert _claim_count(db, evidence_id) == 0

    audit = _latest_audit(db, evidence_id)
    assert audit
    assert audit["outcome"] == "strict_rejected"
    assert audit["detail"] in ("invalid_schema", "claim[0]_missing_object", "claim[0]_missing_support_char_start")


def test_json_strict_quote_mismatch_writes_no_claims(tmp_path: Path):
    db = _db(tmp_path)
    evidence_id = _ingest(db, "FEME must use PostgreSQL as canonical memory.")

    candidates = extract_candidates_for_evidence(
        db,
        evidence_id,
        extractor_mode="json_strict",
        extractor_provider="json_static",
        extractor_config={
            "claims": [
                {
                    "claim_text": "FEME must use PostgreSQL as canonical memory.",
                    "subject": "FEME",
                    "predicate": "must_use",
                    "object": "PostgreSQL as canonical memory",
                    "support_char_start": 0,
                    "support_char_end": 44,
                    "support_quote_text": "Mismatched quote text",
                }
            ]
        },
    )
    assert candidates == []
    assert _claim_count(db, evidence_id) == 0

    audit = _latest_audit(db, evidence_id)
    assert audit
    assert audit["outcome"] == "strict_rejected"
    assert audit["detail"] in ("support_quote_mismatch", "claim[0]_quote_mismatch")


def test_json_with_fallback_uses_heuristic_when_provider_missing(tmp_path: Path):
    db = _db(tmp_path)
    evidence_id = _ingest(db, "FEME must use PostgreSQL as canonical memory.")

    candidates = extract_candidates_for_evidence(
        db,
        evidence_id,
        extractor_mode="json_with_fallback",
        extractor_provider="missing-provider",
    )
    assert candidates

    audit = _latest_audit(db, evidence_id)
    assert audit
    assert audit["outcome"] == "heuristic_fallback"
    assert audit["detail"] == "structured_extractor_unavailable"


def test_heuristic_mode_ignores_json_provider(tmp_path: Path):
    db = _db(tmp_path)
    evidence_id = _ingest(db, "FEME must use PostgreSQL as canonical memory.")

    candidates = extract_candidates_for_evidence(
        db,
        evidence_id,
        extractor_mode="heuristic",
        extractor_provider="json_static",
    )
    assert candidates

    governor = MemoryWriteGovernor(db)
    for candidate in candidates:
        governor.commit_candidate(candidate, project_id="default")

    assert _claim_count(db, evidence_id) > 0
    audit = _latest_audit(db, evidence_id)
    assert audit
    assert audit["outcome"] == "heuristic_success"
