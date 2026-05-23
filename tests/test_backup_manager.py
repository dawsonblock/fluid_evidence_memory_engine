from pathlib import Path

import pytest

from feme.backup import BackupManager
from feme.db import Database


def test_sqlite_backup_still_works(tmp_path: Path):
    db = Database(tmp_path / "memory.sqlite")
    db.init()
    with db.connect() as con:
        con.execute(
            "INSERT INTO projects (id, name, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (
                "prj_1",
                "Project 1",
                "backup fixture",
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:00:00Z",
            ),
        )
        con.commit()

    out = tmp_path / "backup.sqlite"
    result = BackupManager(db).backup(out)
    assert out.exists()
    assert result["backup_path"] == str(out)


def test_postgres_backup_is_explicitly_not_implemented():
    class _PostgresLike:
        backend = "postgres"

    with pytest.raises(NotImplementedError, match="pg_dump|export-project"):
        BackupManager(_PostgresLike()).backup("unused-path")
