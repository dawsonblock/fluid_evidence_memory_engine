from __future__ import annotations

from typing import Any
import importlib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from feme import __version__
from feme.db import Database
from feme.runtime import runtime_health

runner = CliRunner()


def _db(tmp_path: Path) -> Database:
    db = Database(str(tmp_path / "runtime-health.sqlite"))
    db.init()
    return db


def test_runtime_health_reports_complete_migration_state(tmp_path: Path):
    db = _db(tmp_path)

    health = runtime_health(db)

    assert health["package_version"] == __version__
    assert health["schema_version"] == db.schema_version()
    assert health["migration_status"] == "complete"
    assert health["missing_schema_features"] == []
    assert health["last_migration_error"] is None
    assert "last_migration_error_at" in health
    assert health["last_migration_error_at"] is None


def test_runtime_health_surfaces_last_migration_error_metadata(tmp_path: Path):
    db = _db(tmp_path)
    timestamp = "2026-05-24T00:00:00Z"

    with db.connect() as con:
        con.execute(
            "INSERT OR REPLACE INTO schema_meta (key, value, updated_at) VALUES (?, ?, ?)",
            ("last_migration_error", "forced-test-error", timestamp),
        )
        con.execute(
            "INSERT OR REPLACE INTO schema_meta (key, value, updated_at) VALUES (?, ?, ?)",
            ("last_migration_error_at", timestamp, timestamp),
        )
        con.commit()

    health = runtime_health(db)

    assert health["migration_status"] == "failed"
    assert health["last_migration_error"] == "forced-test-error"
    assert health["last_migration_error_at"] == timestamp


def test_runtime_health_reports_incomplete_schema_features(tmp_path: Path):
    db = _db(tmp_path)

    with db.connect() as con:
        con.execute("DROP TRIGGER IF EXISTS trg_memory_ledger_no_update")
        con.commit()

    health = runtime_health(db)

    assert health["migration_status"] == "incomplete"
    assert "trg_memory_ledger_no_update" in health["missing_schema_features"]


def test_runtime_health_cli_reports_migration_status(tmp_path: Path):
    db_path = tmp_path / "cli-runtime.sqlite"
    Database(str(db_path)).init()

    from feme.cli import app

    result = runner.invoke(app, ["runtime-health", "--db", str(db_path)])

    assert result.exit_code == 0
    assert '"migration_status": "complete"' in result.stdout


def test_api_health_exposes_runtime_migration_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    fastapi_testclient = pytest.importorskip("fastapi.testclient")

    monkeypatch.setenv("FEME_DB_BACKEND", "sqlite")
    monkeypatch.setenv("FEME_DB_PATH", str(tmp_path / "api-runtime.sqlite"))
    monkeypatch.delenv("FEME_POSTGRES_DSN", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("FEME_API_AUTH_REQUIRED", "false")

    config = importlib.import_module("feme.config")
    importlib.reload(config)
    api: Any = importlib.import_module("feme.api")
    api = importlib.reload(api)

    db = _db(tmp_path)
    original_db = api.database
    api.database = db
    try:
        client = fastapi_testclient.TestClient(api.app)
        response = client.get("/health")
    finally:
        api.database = original_db

    assert response.status_code == 200
    payload = response.json()
    assert payload["runtime"]["migration_status"] == "complete"
    assert payload["runtime"]["missing_schema_features"] == []
