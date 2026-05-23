from pathlib import Path
from types import SimpleNamespace

import pytest

from feme import claim_extractor
from feme.claim_extractor import (
    ExtractorAuditWriteError,
    extract_candidates_for_evidence,
)
from feme.db import Database
from feme.evidence import EvidenceIngestor
from feme.runtime_pipeline import TransactionalIngestionPipeline


def _db(tmp_path: Path) -> Database:
    db = Database(str(tmp_path / "extractor-audit-failure.sqlite"))
    db.init()
    return db


def test_audit_failure_with_require_false_continues(monkeypatch, tmp_path: Path):
    db = _db(tmp_path)
    evidence = EvidenceIngestor(db).ingest_text(
        "FEME must use PostgreSQL as canonical memory.",
        source_type="official_record",
    )

    def _boom(*args, **kwargs):
        raise RuntimeError("audit storage down")

    monkeypatch.setattr(claim_extractor, "_persist_extractor_audit", _boom)
    warnings: list[str] = []
    candidates = extract_candidates_for_evidence(
        db,
        evidence["evidence_id"],
        extractor_mode="json_with_fallback",
        extractor_provider="missing-provider",
        require_extractor_audit=False,
        audit_warnings=warnings,
    )

    assert candidates
    assert warnings
    assert warnings[0].startswith("audit_write_failed:")


def test_audit_failure_with_require_true_fails_closed(monkeypatch, tmp_path: Path):
    db = _db(tmp_path)

    def _boom(*args, **kwargs):
        raise RuntimeError("audit storage down")

    monkeypatch.setattr(claim_extractor, "_persist_extractor_audit", _boom)
    monkeypatch.setattr(
        "feme.runtime_pipeline.get_settings",
        lambda: SimpleNamespace(
            require_extractor_audit=True,
            extractor_schema_version="claim-extraction-v1",
        ),
    )

    with pytest.raises(ExtractorAuditWriteError):
        TransactionalIngestionPipeline(db).ingest_text(
            "FEME must use PostgreSQL as canonical memory.",
            source_type="official_record",
            extractor_mode="json_with_fallback",
            extractor_provider="missing-provider",
        )

    with db.connect() as con:
        row = con.execute("SELECT COUNT(*) AS n FROM memory_claims").fetchone()
    assert int(row["n"]) == 0
