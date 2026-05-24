from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
from uuid import uuid4

import pytest

from feme.ledger import MemoryLedger
from feme.runtime import make_database
from feme.runtime_pipeline import TransactionalIngestionPipeline


def _is_placeholder_dsn(dsn: str) -> bool:
    parsed = urlparse(dsn)
    host = (parsed.hostname or "").upper()
    user = (parsed.username or "").upper()
    password = (parsed.password or "").upper()
    dbname = parsed.path.lstrip("/").upper()
    placeholders = {"USER", "PASSWORD", "HOST", "DBNAME"}
    return (
        host in placeholders
        or user in placeholders
        or password in placeholders
        or dbname in placeholders
    )


def _live_postgres_dsn() -> str:
    dsn = (
        os.getenv("FEME_DB")
        or os.getenv("FEME_POSTGRES_DSN")
        or os.getenv("DATABASE_URL")
    )
    if not dsn:
        pytest.skip(
            "set FEME_DB or FEME_POSTGRES_DSN (or DATABASE_URL) to run postgres smoke tests"
        )
    if not dsn.startswith(("postgres://", "postgresql://")):
        pytest.skip("FEME_DB must be a PostgreSQL DSN for postgres smoke tests")
    if _is_placeholder_dsn(dsn):
        pytest.skip("FEME_DB appears to be an example DSN; set a real Postgres DSN")
    return dsn


def test_postgres_concurrency_smoke_parallel_writes():
    pytest.importorskip("psycopg")
    db = make_database(_live_postgres_dsn())
    db.init()

    project_id = f"pgconc_{uuid4().hex[:10]}"

    def _ingest(i: int) -> str:
        pipeline = TransactionalIngestionPipeline(db)
        result = pipeline.ingest_text(
            text=f"Concurrency smoke document {i}. Parallel writer validation.",
            source_type="official_record",
            title=f"smoke-concurrency-{i}",
            project_id=project_id,
            actor="pytest-smoke",
            extract_claims=False,
            rebuild_clusters=False,
        )
        return result["evidence_id"]

    with ThreadPoolExecutor(max_workers=5) as pool:
        evidence_ids = list(pool.map(_ingest, range(25)))

    assert len(evidence_ids) == 25
    assert len(set(evidence_ids)) == 25

    with db.connect() as con:
        row = con.execute(
            "SELECT COUNT(*) AS n FROM evidence_sources WHERE project_id = ?",
            (project_id,),
        ).fetchone()

    assert int(row["n"]) == 25

    verify = MemoryLedger(db).verify_chain(project_id=project_id)
    assert verify["ok"] is True
