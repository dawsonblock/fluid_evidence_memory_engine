from __future__ import annotations

import os
from urllib.parse import urlparse
from uuid import uuid4

import pytest

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
    dsn = os.getenv("FEME_DB")
    if not dsn:
        pytest.skip("set FEME_DB to run postgres smoke tests")
    if not dsn.startswith(("postgres://", "postgresql://")):
        pytest.skip("FEME_DB must be a PostgreSQL DSN for postgres smoke tests")
    if _is_placeholder_dsn(dsn):
        pytest.skip("FEME_DB appears to be an example DSN; set a real Postgres DSN")
    return dsn


def test_postgres_load_smoke_ingests_100_documents():
    pytest.importorskip("psycopg")
    db = make_database(_live_postgres_dsn())
    db.init()

    project_id = f"pgload_{uuid4().hex[:10]}"
    pipeline = TransactionalIngestionPipeline(db)

    for i in range(100):
        result = pipeline.ingest_text(
            text=f"Smoke load document {i}. PostgreSQL load path validation.",
            source_type="official_record",
            title=f"smoke-load-{i}",
            project_id=project_id,
            actor="pytest-smoke",
            extract_claims=False,
            rebuild_clusters=False,
        )
        assert result["evidence_id"].startswith("ev_")

    with db.connect() as con:
        row = con.execute(
            "SELECT COUNT(*) AS n FROM evidence_sources WHERE project_id = ?",
            (project_id,),
        ).fetchone()

    assert int(row["n"]) == 100
