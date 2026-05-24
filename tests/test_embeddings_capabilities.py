from __future__ import annotations

from pathlib import Path

from feme.db import Database
from feme.embeddings import embedding_runtime_capabilities


def _sqlite_db(tmp_path: Path) -> Database:
    db = Database(str(tmp_path / "embeddings-capability.sqlite"))
    db.init()
    return db


def test_embedding_capabilities_default_to_hashing_for_sqlite(tmp_path: Path):
    db = _sqlite_db(tmp_path)
    caps = embedding_runtime_capabilities(db)
    assert caps["provider"] == "hashing-embedding-v1"
    assert caps["provider_name"] == "hashing"
    assert caps["provider_version"] == "0.8.1"
    assert int(caps["provider_dimensions"]) == 256
    assert caps["mode"] == "hashing"
    assert caps["pgvector_database_enabled"] is False


def test_embedding_capabilities_pgvector_mode_when_both_probes_true(monkeypatch):
    class _FakeCon:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, _sql, _params=()):
            return self

        def fetchone(self):
            return {"ok": 1}

    class _FakePostgresDB:
        backend = "postgres"

        def connect(self):
            return _FakeCon()

    monkeypatch.setattr("feme.embeddings._has_python_pgvector", lambda: True)
    caps = embedding_runtime_capabilities(_FakePostgresDB())
    assert caps["pgvector_python_available"] is True
    assert caps["pgvector_database_enabled"] is True
    assert caps["mode"] == "pgvector"
