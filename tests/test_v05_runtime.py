from __future__ import annotations

from pathlib import Path

from feme.claim_canonicalizer import ClaimCanonicalizer
from feme.db import Database
from feme.ledger import MemoryLedger
from feme.retrieval_eval_suite import RetrievalEvalSuite
from feme.runtime import runtime_health
from feme.runtime_pipeline import TransactionalIngestionPipeline
from feme.storage import SQLiteStore


def _db(tmp_path: Path) -> Database:
    db = Database(str(tmp_path / "runtime.sqlite"))
    db.init()
    return db


def test_v05_schema_migration_runtime_health_and_store(tmp_path: Path):
    db = _db(tmp_path)
    assert db.schema_version() in {"0.5.0", "0.6.0", "0.7.0"}
    health = runtime_health(db)
    assert health["health"]["ok"] is True
    store = SQLiteStore(db)
    assert store.capabilities().transactions is True
    with store.transaction() as con:
        con.execute(
            "INSERT OR IGNORE INTO projects (id, name, created_at, updated_at, metadata_json) VALUES (?, ?, ?, ?, ?)",
            ("tx", "tx", "now", "now", "{}"),
        )
    rows = store.execute("SELECT id FROM projects WHERE id = ?", ("tx",))
    assert rows[0]["id"] == "tx"


def test_governed_ingestion_writes_ledger_and_clusters(tmp_path: Path):
    db = _db(tmp_path)
    result = TransactionalIngestionPipeline(db).ingest_text(
        "Memory system should use PostgreSQL. Memory system should link claims to spans. The review happened on March 4, 2024.",
        source_type="official_record",
        title="runtime sample",
        actor="test",
    )
    assert result["evidence_id"].startswith("ev_")
    assert result["claim_writes"]
    ledger = MemoryLedger(db)
    events = ledger.list(limit=50)
    assert any(e["event_type"] == "ingestion_finished" for e in events)
    assert ledger.verify_chain()["ok"] is True
    clusters = ClaimCanonicalizer(db).list_clusters()
    assert clusters


def test_retrieval_eval_suite(tmp_path: Path):
    db = _db(tmp_path)
    TransactionalIngestionPipeline(db).ingest_text(
        "Use PostgreSQL as canonical memory. Claims must link to exact spans.",
        source_type="official_record",
    )
    suite = RetrievalEvalSuite(db)
    case = suite.add_case(
        query="canonical memory database", expected_terms=["PostgreSQL"]
    )
    assert case["id"].startswith("evalcase_")
    result = suite.run()
    assert result["case_count"] == 1
    assert result["passed"] == 1
