import json
from pathlib import Path

from feme.claim_extractor import extract_candidates_for_evidence
from feme.db import Database
from feme.evidence import EvidenceIngestor


def _db(tmp_path: Path) -> Database:
    db = Database(str(tmp_path / "extractor-audit.sqlite"))
    db.init()
    return db


def test_extractor_audit_records_provider_metadata_json(tmp_path: Path):
    db = _db(tmp_path)
    text = "FEME must use PostgreSQL as canonical memory."
    evidence = EvidenceIngestor(db).ingest_text(
        text,
        source_type="official_record",
    )

    extract_candidates_for_evidence(
        db,
        evidence["evidence_id"],
        extractor_mode="json_with_fallback",
        extractor_provider="json_static",
        extractor_schema_version="claim-extraction-v1",
        extractor_config={
            "claims": [
                {
                    "claim_text": "FEME must use PostgreSQL as canonical memory.",
                    "subject": "FEME",
                    "predicate": "must_use",
                    "object": "PostgreSQL as canonical memory",
                    "support_char_start": 0,
                    "support_char_end": len(text),
                    "support_quote_text": text,
                }
            ]
        },
    )

    with db.connect() as con:
        row = con.execute(
            """
            SELECT outcome, metadata_json
            FROM extractor_audit
            WHERE evidence_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (evidence["evidence_id"],),
        ).fetchone()

    assert row
    assert row["outcome"] == "structured_success"
    metadata = json.loads(row["metadata_json"])
    assert metadata["provider_name"] == "json_static"
    assert metadata["provider_version"] == "0.1.0"
    assert metadata["schema_version"] == "claim-extraction-v1"
    assert metadata["strict_mode"] is False
    assert metadata["fallback_used"] is False
    assert metadata["error_type"] is None
    assert str(metadata["config_hash"]).startswith("sha256:")
