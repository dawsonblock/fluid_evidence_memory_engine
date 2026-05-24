from __future__ import annotations

from typing import Any

from .db import (
    MIGRATION_STATUS_COMPLETE,
    MIGRATION_STATUS_FAILED,
    MIGRATION_STATUS_INCOMPLETE,
    SCHEMA_VERSION,
    read_schema_meta,
    write_schema_meta,
)
from .postgres_db import POSTGRES_SCHEMA_VERSION


def check_migration_completeness(db: Any) -> dict[str, Any]:
    backend = str(getattr(db, "backend", "sqlite")).lower()
    expected_schema_version = (
        POSTGRES_SCHEMA_VERSION if backend == "postgres" else SCHEMA_VERSION
    )
    last_migration_error = read_schema_meta(db, "last_migration_error")
    last_migration_error_at = read_schema_meta(db, "last_migration_error_at")
    schema_version = read_schema_meta(db, "schema_version")

    with db.connect() as con:
        missing = _missing_schema_features(
            con,
            backend,
            expected_schema_version,
        )

    if last_migration_error:
        migration_status = MIGRATION_STATUS_FAILED
    elif missing:
        migration_status = MIGRATION_STATUS_INCOMPLETE
    else:
        migration_status = MIGRATION_STATUS_COMPLETE

    return {
        "backend": backend,
        "schema_version": schema_version,
        "expected_schema_version": expected_schema_version,
        "migration_status": migration_status,
        "missing_schema_features": missing,
        "last_migration_error": last_migration_error,
        "last_migration_error_at": last_migration_error_at,
    }


def sync_migration_health(db: Any) -> dict[str, Any]:
    health = check_migration_completeness(db)
    write_schema_meta(
        db,
        {
            "migration_status": health["migration_status"],
            "last_migration_error": health["last_migration_error"],
            "last_migration_error_at": health["last_migration_error_at"],
        },
    )
    return health


def _missing_schema_features(
    con: Any,
    backend: str,
    expected_schema_version: str,
) -> list[str]:
    missing: list[str] = []
    if not _has_schema_version(con, expected_schema_version):
        missing.append("schema_meta.schema_version")
    if not _table_exists(con, backend, "claim_support_spans"):
        missing.append("claim_support_spans")
    if not _table_exists(con, backend, "api_request_audit"):
        missing.append("api_request_audit")
    if not _table_exists(con, backend, "extractor_audit"):
        missing.append("extractor_audit")
    if not _index_exists(con, backend, "idx_evidence_project_sha_unique"):
        missing.append("idx_evidence_project_sha_unique")

    embeddings_columns = _column_names(con, backend, "embeddings")
    for name in ("provider", "dimensions", "config_hash"):
        if name not in embeddings_columns:
            missing.append(f"embeddings.{name}")

    link_columns = _column_names(con, backend, "claim_evidence_links")
    if "evidence_kind" not in link_columns:
        missing.append("claim_evidence_links.evidence_kind")

    if backend == "postgres":
        if not _trigger_exists(
            con,
            backend,
            "trg_memory_ledger_block_mutation",
        ):
            missing.append("trg_memory_ledger_block_mutation")
    else:
        for name in (
            "trg_memory_ledger_no_update",
            "trg_memory_ledger_no_delete",
        ):
            if not _trigger_exists(con, backend, name):
                missing.append(name)
    return missing


def _has_schema_version(con: Any, expected_schema_version: str) -> bool:
    row = con.execute(
        "SELECT value FROM schema_meta WHERE key = ?",
        ("schema_version",),
    ).fetchone()
    return bool(row and row["value"] == expected_schema_version)


def _table_exists(con: Any, backend: str, name: str) -> bool:
    if backend == "postgres":
        row = con.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = current_schema() AND table_name = ?
            LIMIT 1
            """,
            (name,),
        ).fetchone()
    else:
        row = con.execute(
            (
                "SELECT 1 FROM sqlite_master "
                "WHERE type = 'table' AND name = ? LIMIT 1"
            ),
            (name,),
        ).fetchone()
    return row is not None


def _index_exists(con: Any, backend: str, name: str) -> bool:
    if backend == "postgres":
        row = con.execute(
            """
            SELECT 1
            FROM pg_indexes
            WHERE schemaname = current_schema() AND indexname = ?
            LIMIT 1
            """,
            (name,),
        ).fetchone()
    else:
        row = con.execute(
            (
                "SELECT 1 FROM sqlite_master "
                "WHERE type = 'index' AND name = ? LIMIT 1"
            ),
            (name,),
        ).fetchone()
    return row is not None


def _trigger_exists(con: Any, backend: str, name: str) -> bool:
    if backend == "postgres":
        row = con.execute(
            """
            SELECT 1
            FROM pg_trigger t
            JOIN pg_class c ON c.oid = t.tgrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = current_schema()
              AND t.tgname = ?
              AND NOT t.tgisinternal
            LIMIT 1
            """,
            (name,),
        ).fetchone()
    else:
        row = con.execute(
            (
                "SELECT 1 FROM sqlite_master "
                "WHERE type = 'trigger' AND name = ? LIMIT 1"
            ),
            (name,),
        ).fetchone()
    return row is not None


def _column_names(con: Any, backend: str, table_name: str) -> set[str]:
    if backend == "postgres":
        rows = con.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = ?
            """,
            (table_name,),
        ).fetchall()
        return {row["column_name"] for row in rows}
    rows = con.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}
