from __future__ import annotations

from pathlib import Path

from feme.db import Database, read_schema_meta
from feme.migration_health import check_migration_completeness, sync_migration_health


def _db(tmp_path: Path) -> Database:
    db = Database(str(tmp_path / "migration-health.sqlite"))
    db.init()
    return db


def test_fresh_sqlite_init_reports_complete_migration_health(tmp_path: Path):
    db = _db(tmp_path)

    health = check_migration_completeness(db)

    assert health["schema_version"] == db.schema_version()
    assert health["migration_status"] == "complete"
    assert health["missing_schema_features"] == []
    assert health["last_migration_error"] is None
    assert read_schema_meta(db, "migration_status") == "complete"


def test_missing_schema_features_report_incomplete_status(tmp_path: Path):
    db = _db(tmp_path)

    with db.connect() as con:
        con.execute("DROP TRIGGER IF EXISTS trg_memory_ledger_no_update")
        con.execute("DROP INDEX IF EXISTS idx_evidence_project_sha_unique")
        con.commit()

    health = sync_migration_health(db)

    assert health["migration_status"] == "incomplete"
    assert "trg_memory_ledger_no_update" in health["missing_schema_features"]
    assert "idx_evidence_project_sha_unique" in health["missing_schema_features"]
    assert read_schema_meta(db, "migration_status") == "incomplete"
