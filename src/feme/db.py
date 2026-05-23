from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .utils import now_iso

ROOT_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "sql" / "sqlite_schema.sql"
PACKAGE_SCHEMA_PATH = Path(__file__).resolve().parent / "sqlite_schema.sql"
SCHEMA_VERSION = "0.7.3"


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
                "INSERT OR IGNORE INTO projects (id, name, description, created_at, updated_at, metadata_json) VALUES (?, ?, ?, ?, ?, ?)",
                ("default", "default", "Default project", now, now, "{}"),
            )
            con.commit()
        # Apply idempotent runtime migrations after the base schema.
        try:
            from .migrations import MigrationManager

            MigrationManager(self).apply_all()
        except Exception:
            # Keep bootstrap resilient; integrity-check and migrate expose failures.
            pass
        # Import here to avoid a module import cycle during schema bootstrapping.
        try:
            from .source_registry import SourceRegistry

            SourceRegistry(self).ensure_defaults(project_id="default")
        except Exception:
            # Schema initialization should not fail because optional defaults could
            # not be inserted. Integrity checks will report the missing registry.
            pass

    def schema_version(self) -> str | None:
        with self.connect() as con:
            try:
                row = con.execute(
                    "SELECT value FROM schema_meta WHERE key = 'schema_version'"
                ).fetchone()
            except sqlite3.OperationalError:
                return None
        return row["value"] if row else None


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]
