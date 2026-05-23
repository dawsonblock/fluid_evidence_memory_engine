from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from uuid import uuid4

import pytest

from feme.export_import import ProjectExporter
from feme.integrity import IntegrityChecker
from feme.ledger import MemoryLedger
from feme.maintenance import MaintenanceManager
from feme.migrations import MigrationManager
from feme.retention import RetentionManager
from feme.retrieval import RetrievalPlanner
from feme.runtime import make_database, runtime_health
from feme.runtime_pipeline import TransactionalIngestionPipeline
from feme.evidence import EvidenceIngestor
from feme.source_registry import SourceRegistry


def _live_postgres_dsn() -> str:
    dsn = os.getenv("FEME_TEST_POSTGRES_DSN") or os.getenv("FEME_POSTGRES_DSN")
    if not dsn:
        pytest.skip(
            "set FEME_TEST_POSTGRES_DSN (or FEME_POSTGRES_DSN) to run live Postgres integration tests"
        )
    return dsn


@pytest.fixture()
def postgres_db():
    pytest.importorskip("psycopg")
    db = make_database(_live_postgres_dsn())
    db.init()
    return db


@pytest.fixture()
def project_id() -> str:
    return f"pgtest_{uuid4().hex[:12]}"


def test_postgres_governed_ingest_retrieve_and_ledger_verify(
    postgres_db, project_id: str
):
    migration = MigrationManager(postgres_db).apply_all()
    # Base schema may already include earlier migrations; only assert successful
    # migration execution and expected schema version.
    assert isinstance(migration["applied"], list)
    assert migration["schema_version"] in {
        "0.5.0",
        "0.6.0",
        "0.7.0",
        "0.7.1",
        "0.7.2",
        "0.7.3",
    }

    text = (
        "Memory engine must use PostgreSQL as the canonical database. "
        "Memory engine links claims to exact evidence spans."
    )
    run = TransactionalIngestionPipeline(postgres_db).ingest_text(
        text,
        source_type="official_record",
        title="live pg ingest",
        project_id=project_id,
        actor="pytest",
    )

    assert run["evidence_id"].startswith("ev_")
    assert run[
        "claim_writes"
    ], "expected claim extraction + governed writes on live Postgres"

    results = RetrievalPlanner(postgres_db).search(
        "canonical database", project_id=project_id, top_k=5
    )
    assert results
    assert any("PostgreSQL" in r.text for r in results)

    fts = MaintenanceManager(postgres_db).rebuild_fts(project_id=project_id)
    assert fts["backend"] == "postgres"
    assert fts["claims_indexed"] >= 1
    with postgres_db.connect() as con:
        row = con.execute(
            "SELECT COUNT(*) AS n FROM memory_claims WHERE project_id = ? AND claim_tsv IS NOT NULL",
            (project_id,),
        ).fetchone()
        chunk_row = con.execute(
            """
            SELECT COUNT(*) AS n
            FROM text_chunks tc
            JOIN evidence_sources es ON es.id = tc.evidence_id
            WHERE es.project_id = ? AND tc.chunk_tsv IS NOT NULL
            """,
            (project_id,),
        ).fetchone()
    assert int(row["n"]) >= 1
    assert int(chunk_row["n"]) >= 1

    verify = MemoryLedger(postgres_db).verify_chain(project_id=project_id)
    assert verify["ok"] is True


def test_postgres_init_and_migrate(postgres_db):
    migration = MigrationManager(postgres_db).apply_all()
    assert isinstance(migration["applied"], list)
    assert migration["schema_version"] in {
        "0.5.0",
        "0.6.0",
        "0.7.0",
        "0.7.1",
        "0.7.2",
        "0.7.3",
    }


def test_postgres_export_import_redaction_and_integrity(
    postgres_db, project_id: str, tmp_path
):
    text = (
        "The evidence memory runtime should preserve audit integrity. "
        "The memory runtime stores token spans for citation grounding."
    )
    run = TransactionalIngestionPipeline(postgres_db).ingest_text(
        text,
        source_type="official_record",
        title="live pg export",
        project_id=project_id,
        actor="pytest",
    )

    export_path = tmp_path / f"{project_id}.json"
    exported = ProjectExporter(postgres_db).export_project(project_id, export_path)
    assert export_path.exists()
    assert exported["project_id"] == project_id

    imported = ProjectExporter(postgres_db).import_project(export_path, replace=False)
    assert imported["project_id"] == project_id

    integrity_before = IntegrityChecker(postgres_db).run(project_id=project_id)
    assert integrity_before["ok"] is True

    redaction = RetentionManager(postgres_db).redact_evidence(
        run["evidence_id"], actor="pytest", reason="integration test"
    )
    assert redaction["redacted"] is True

    integrity_after = IntegrityChecker(postgres_db).run(project_id=project_id)
    assert integrity_after["ok"] is True


def test_postgres_api_smoke(postgres_db, project_id: str):
    pytest.importorskip("httpx")
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from feme import api

    original_db = api.database
    api.database = postgres_db
    try:
        client = fastapi_testclient.TestClient(api.app)

        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        ingest = client.post(
            "/ingest/governed",
            json={
                "text": "API ingest must support PostgreSQL runtime paths.",
                "source_type": "official_record",
                "title": "api smoke",
                "project_id": project_id,
                "actor": "pytest",
                "extract_claims": True,
            },
        )
        assert ingest.status_code == 200
        payload = ingest.json()
        assert payload["evidence_id"].startswith("ev_")

        search = client.post(
            "/search",
            json={"query": "PostgreSQL runtime", "project_id": project_id, "top_k": 5},
        )
        assert search.status_code == 200
        assert isinstance(search.json(), list)
    finally:
        api.database = original_db


def test_postgres_ledger_append_is_serialized_under_concurrency(
    postgres_db, project_id: str
):
    ledger = MemoryLedger(postgres_db)

    def _append(i: int) -> str:
        item = ledger.append(
            event_type="concurrency_test",
            object_type="unit",
            object_id=f"obj_{i}",
            project_id=project_id,
            actor="pytest",
            after={"i": i},
        )
        return item["id"]

    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(_append, range(20)))

    assert len(ids) == 20
    verify = ledger.verify_chain(project_id=project_id)
    assert verify["ok"] is True


def test_postgres_ledger_is_append_only(postgres_db, project_id: str):
    ledger = MemoryLedger(postgres_db)
    item = ledger.append(
        event_type="append_only_test",
        object_type="unit",
        object_id="immutable",
        project_id=project_id,
        actor="pytest",
        after={"ok": True},
    )

    with pytest.raises(Exception):
        with postgres_db.connect() as con:
            con.execute(
                "UPDATE memory_ledger SET reason = ? WHERE id = ?",
                ("mutated", item["id"]),
            )
            con.commit()

    with pytest.raises(Exception):
        with postgres_db.connect() as con:
            con.execute(
                "DELETE FROM memory_ledger WHERE id = ?",
                (item["id"],),
            )
            con.commit()


def test_postgres_duplicate_evidence_parallel_writers(postgres_db, project_id: str):
    text = "Parallel Postgres writers should collapse duplicate evidence rows."

    def _ingest_once(_i: int) -> dict:
        return EvidenceIngestor(postgres_db).ingest_text(
            text,
            source_type="official_record",
            project_id=project_id,
            deduplicate=False,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(_ingest_once, range(20)))

    evidence_ids = {r["evidence_id"] for r in results}
    assert len(evidence_ids) == 1
    assert any(r["duplicate"] is False for r in results)
    assert any(r["duplicate"] is True for r in results)

    with postgres_db.connect() as con:
        row = con.execute(
            "SELECT sha256 FROM evidence_sources WHERE id = ?",
            (next(iter(evidence_ids)),),
        ).fetchone()
        n = con.execute(
            "SELECT COUNT(*) AS n FROM evidence_sources WHERE project_id = ? AND sha256 = ?",
            (project_id, row["sha256"]),
        ).fetchone()["n"]
    assert int(n) == 1


def test_postgres_source_registry_review_required(postgres_db, project_id: str):
    registry = SourceRegistry(postgres_db)
    registry.upsert(
        "user_note",
        project_id=project_id,
        enabled=True,
        review_required=True,
        default_quality=0.45,
    )

    ingest = EvidenceIngestor(postgres_db).ingest_text(
        "User note should require review for downstream governance.",
        source_type="user_note",
        project_id=project_id,
    )
    assert ingest["source_review_required"] is True

    rule = registry.assert_enabled("user_note", project_id=project_id)
    assert bool(rule["review_required"]) is True


def test_postgres_native_fts_path(postgres_db, project_id: str):
    TransactionalIngestionPipeline(postgres_db).ingest_text(
        "FEME uses PostgreSQL for canonical memory retrieval in live runtime tests.",
        source_type="official_record",
        title="fts proof",
        project_id=project_id,
        actor="pytest",
    )
    results = RetrievalPlanner(postgres_db).search(
        "canonical memory",
        project_id=project_id,
        top_k=5,
    )
    assert results
    assert any(r.metadata.get("backend") == "postgres" for r in results)
    assert any(r.metadata.get("search_mode") == "postgres_fts" for r in results)


def test_runtime_health_reports_postgres_backend(postgres_db):
    health = runtime_health(postgres_db)
    assert health["health"]["backend"] == "postgres"
    assert health["health"]["ok"] is True
    assert health["embeddings"]["provider"] == "hashing-embedding-v1"
    assert health["embeddings"]["mode"] in {"hashing", "pgvector"}
