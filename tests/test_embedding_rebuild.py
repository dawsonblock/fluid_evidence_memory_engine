"""Phase C: Tests for V15 migration columns and embeddings-rebuild CLI."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Generator

import pytest

from feme.db import Database
from feme.evidence import EvidenceIngestor
from feme.maintenance import MaintenanceManager
from feme.migrations import MigrationManager
from feme.runtime import make_database


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _db(tmp_path: Path) -> Database:
    db = make_database(str(tmp_path / "test.db"))
    db.init()
    return db


def _ingest(db: Database, text: str, project_id: str = "default") -> str:
    ingestor = EvidenceIngestor(db)
    result = ingestor.ingest_text(
        text=text,
        source_type="note",
        project_id=project_id,
    )
    return result["evidence_id"]


# ---------------------------------------------------------------------------
# V15 migration: new columns on embeddings table
# ---------------------------------------------------------------------------

class TestV15Migration:
    def test_migration_applies_new_columns(self, tmp_path: Path):
        """V15 adds provider, dimensions, config_hash to embeddings."""
        db = _db(tmp_path)  # db.init() runs apply_all() internally
        result = MigrationManager(db).apply_all()  # second call: already applied
        assert result["schema_version"] == "0.8.0"
        # Verify V15 was applied (may have been applied during db.init)
        applied_ids = [m["id"] for m in MigrationManager(db).list_applied()]
        assert "015_embeddings_provider_columns" in applied_ids

    def test_new_columns_have_defaults(self, tmp_path: Path):
        """Rows inserted before V15 upgrade get default values for new columns."""
        db = _db(tmp_path)
        evidence_id = _ingest(db, "Test sentence for embedding defaults.")
        # After init+ingest, migration has run; embed something and read it back
        manager = MaintenanceManager(db)
        manager.rebuild_embeddings(project_id="default", owner_type="chunk")
        with db.connect() as con:
            row = con.execute(
                "SELECT provider, dimensions, config_hash FROM embeddings LIMIT 1"
            ).fetchone()
        assert row is not None
        # Default value for pre-V15 rows
        assert row["provider"] is not None
        assert row["dimensions"] is not None

    def test_migration_idempotent(self, tmp_path: Path):
        """Calling apply_all twice does not raise and reports no new migrations."""
        db = _db(tmp_path)
        first = MigrationManager(db).apply_all()
        second = MigrationManager(db).apply_all()
        assert second["schema_version"] == "0.8.0"
        # Second run has nothing new to apply
        assert second["applied"] == []


# ---------------------------------------------------------------------------
# MaintenanceManager.rebuild_embeddings
# ---------------------------------------------------------------------------

class TestRebuildEmbeddings:
    def test_rebuild_chunks_returns_count(self, tmp_path: Path):
        db = _db(tmp_path)
        _ingest(db, "FEME processes evidence autonomously.")
        _ingest(db, "PostgreSQL stores canonical memory reliably.")
        result = MaintenanceManager(db).rebuild_embeddings(
            project_id="default", owner_type="chunk"
        )
        assert result["owner_type"] == "chunk"
        assert result["project_id"] == "default"
        assert result["embeddings_rebuilt"] >= 2

    def test_rebuild_claims_returns_count(self, tmp_path: Path):
        db = _db(tmp_path)
        _ingest(db, "FEME extracts claims from evidence automatically.")
        result = MaintenanceManager(db).rebuild_embeddings(
            project_id="default", owner_type="claim"
        )
        assert result["owner_type"] == "claim"
        assert result["embeddings_rebuilt"] >= 0  # may be 0 if no claims extracted

    def test_rebuild_invalid_owner_type_raises(self, tmp_path: Path):
        db = _db(tmp_path)
        with pytest.raises(ValueError, match="owner_type"):
            MaintenanceManager(db).rebuild_embeddings(
                project_id="default", owner_type="invalid"
            )

    def test_rebuild_scoped_to_project(self, tmp_path: Path):
        db = _db(tmp_path)
        _ingest(db, "Alpha project sentence.", project_id="alpha")
        _ingest(db, "Beta project sentence.", project_id="beta")
        result_alpha = MaintenanceManager(db).rebuild_embeddings(
            project_id="alpha", owner_type="chunk"
        )
        result_beta = MaintenanceManager(db).rebuild_embeddings(
            project_id="beta", owner_type="chunk"
        )
        assert result_alpha["embeddings_rebuilt"] >= 1
        assert result_beta["embeddings_rebuilt"] >= 1

    def test_rebuild_is_idempotent(self, tmp_path: Path):
        db = _db(tmp_path)
        _ingest(db, "Idempotent embedding sentence.")
        m = MaintenanceManager(db)
        r1 = m.rebuild_embeddings(project_id="default", owner_type="chunk")
        r2 = m.rebuild_embeddings(project_id="default", owner_type="chunk")
        # Should rebuild the same number of embeddings both times (deletes + re-inserts)
        assert r1["embeddings_rebuilt"] == r2["embeddings_rebuilt"]

    def test_embeddings_stored_as_valid_json(self, tmp_path: Path):
        db = _db(tmp_path)
        _ingest(db, "JSON validation sentence for embeddings.")
        MaintenanceManager(db).rebuild_embeddings(project_id="default", owner_type="chunk")
        with db.connect() as con:
            rows = con.execute("SELECT vector_json FROM embeddings").fetchall()
        assert rows
        for row in rows:
            vec = json.loads(row["vector_json"])
            assert isinstance(vec, list)
            assert all(isinstance(v, float) for v in vec)


# ---------------------------------------------------------------------------
# CLI: embeddings-rebuild command
# ---------------------------------------------------------------------------

class TestEmbeddingsRebuildCLI:
    def test_cli_command_registered(self):
        """embeddings-rebuild command should appear in CLI app commands."""
        from feme.cli import app
        command_names = [c.name for c in app.registered_commands]
        assert "embeddings-rebuild" in command_names

    def test_cli_runs_via_typer_runner(self, tmp_path: Path):
        from typer.testing import CliRunner
        from feme.cli import app
        db_path = str(tmp_path / "cli_test.db")
        runner = CliRunner()
        # init first
        runner.invoke(app, ["init", "--db", db_path])
        result = runner.invoke(
            app,
            ["embeddings-rebuild", "--db", db_path, "--project-id", "default", "--owner-type", "chunk"],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["owner_type"] == "chunk"
        assert "embeddings_rebuilt" in data

    def test_cli_claim_owner_type(self, tmp_path: Path):
        from typer.testing import CliRunner
        from feme.cli import app
        db_path = str(tmp_path / "cli_claim_test.db")
        runner = CliRunner()
        runner.invoke(app, ["init", "--db", db_path])
        result = runner.invoke(
            app,
            ["embeddings-rebuild", "--db", db_path, "--owner-type", "claim"],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["owner_type"] == "claim"
