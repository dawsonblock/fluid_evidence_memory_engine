from __future__ import annotations

from pathlib import Path

import pytest

from feme import migrations
from feme.db import Database, read_schema_meta


def _db(tmp_path: Path) -> Database:
    return Database(str(tmp_path / "strict-init.sqlite"))


def test_init_raises_on_migration_failure_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    def _boom(self):
        raise RuntimeError("boom")

    monkeypatch.delenv("FEME_LENIENT_INIT", raising=False)
    monkeypatch.setattr(migrations.MigrationManager, "apply_all", _boom)

    db = _db(tmp_path)
    with pytest.raises(RuntimeError, match="boom"):
        db.init()

    assert read_schema_meta(db, "migration_status") == "failed"
    assert read_schema_meta(db, "last_migration_error") == "boom"
    assert read_schema_meta(db, "last_migration_error_at") is not None


def test_init_records_failure_when_lenient_mode_enabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    def _boom(self):
        raise RuntimeError("boom")

    monkeypatch.setenv("FEME_LENIENT_INIT", "true")
    monkeypatch.setattr(migrations.MigrationManager, "apply_all", _boom)

    db = _db(tmp_path)
    db.init()

    assert read_schema_meta(db, "migration_status") == "failed"
    assert read_schema_meta(db, "last_migration_error") == "boom"
    assert read_schema_meta(db, "last_migration_error_at") is not None
