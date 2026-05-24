from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .utils import now_iso

ROOT_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "sql" / "sqlite_schema.sql"
PACKAGE_SCHEMA_PATH = Path(__file__).resolve().parent / "sqlite_schema.sql"
SCHEMA_VERSION = "0.8.1"
MIGRATION_STATUS_COMPLETE = "complete"
MIGRATION_STATUS_FAILED = "failed"
MIGRATION_STATUS_INCOMPLETE = "incomplete"


class Database:
    def __init__(self, path: str):
        self.path = path

    def connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        return con

    def init(self) -> None:
        schema_path = (
            ROOT_SCHEMA_PATH if ROOT_SCHEMA_PATH.exists() else PACKAGE_SCHEMA_PATH
        )
        schema = schema_path.read_text(encoding="utf-8")
        with self.connect() as con:
            con.executescript(schema)
            now = now_iso()
            con.execute(
                "INSERT OR REPLACE INTO schema_meta (key, value, updated_at) VALUES (?, ?, ?)",
                ("schema_version", SCHEMA_VERSION, now),
            )
            con.execute(
                "INSERT OR REPLACE INTO schema_meta (key, value, updated_at) VALUES (?, ?, ?)",
                ("migration_status", MIGRATION_STATUS_INCOMPLETE, now),
            )
            con.execute(
                "INSERT OR IGNORE INTO projects (id, name, description, created_at, updated_at, metadata_json) VALUES (?, ?, ?, ?, ?, ?)",
                ("default", "default", "Default project", now, now, "{}"),
            )
            con.commit()
        # Apply idempotent runtime migrations after the base schema.
        try:
            from .migrations import MigrationManager
            from .migration_health import sync_migration_health

            MigrationManager(self).apply_all()
        except Exception as exc:
            record_migration_failure(self, exc)
            if not _env_flag_enabled("FEME_LENIENT_INIT"):
                raise
        else:
            clear_migration_failure(self)
            sync_migration_health(self)
        # Import here to avoid a module import cycle during schema bootstrapping.
        try:
            from .source_registry import SourceRegistry

            SourceRegistry(self).ensure_defaults(project_id="default")
        except Exception:
            # Schema initialization should not fail because optional defaults could
            # not be inserted. Integrity checks will report the missing registry.
            pass

    def schema_version(self) -> str | None:
        return read_schema_meta(self, "schema_version")


def _env_flag_enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes"}


def read_schema_meta(db: Any, key: str) -> str | None:
    with db.connect() as con:
        try:
            row = con.execute(
                "SELECT value FROM schema_meta WHERE key = ?",
                (key,),
            ).fetchone()
        except Exception:
            return None
    return row["value"] if row else None


def write_schema_meta(db: Any, values: dict[str, str | None]) -> None:
    now = now_iso()
    with db.connect() as con:
        for key, value in values.items():
            if value is None:
                con.execute("DELETE FROM schema_meta WHERE key = ?", (key,))
                continue
            con.execute(
                "INSERT OR REPLACE INTO schema_meta (key, value, updated_at) VALUES (?, ?, ?)",
                (key, value, now),
            )
        con.commit()


def record_migration_failure(db: Any, exc: Exception) -> None:
    write_schema_meta(
        db,
        {
            "migration_status": MIGRATION_STATUS_FAILED,
            "last_migration_error": str(exc),
            "last_migration_error_at": now_iso(),
        },
    )


def clear_migration_failure(db: Any) -> None:
    write_schema_meta(
        db,
        {
            "last_migration_error": None,
            "last_migration_error_at": None,
        },
    )


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]
