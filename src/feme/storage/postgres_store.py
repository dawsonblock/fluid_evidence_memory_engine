from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from ..postgres_db import PostgresDatabase, _redact_dsn
from .base import StoreCapabilities, StoreHealth


class PostgresStore:
    """PostgreSQL runtime adapter.

    This adapter now opens a real psycopg-backed PostgresDatabase facade and can
    execute the SQLite-style qmark SQL emitted by FEME through the compatibility
    translator in `postgres_db.py`.
    """

    def __init__(self, dsn: str):
        self.dsn = dsn
        self.db = PostgresDatabase(dsn)

    def capabilities(self) -> StoreCapabilities:
        return StoreCapabilities(
            backend="postgres",
            transactions=True,
            full_text_search=True,
            vector_search=False,
            concurrent_writes=True,
            advisory_locks=True,
        )

    def health(self) -> StoreHealth:
        try:
            self.db.init()
            version = self.db.schema_version()
            return StoreHealth(
                backend="postgres",
                ok=True,
                schema_version=version,
                details={"dsn": _redact_dsn(self.dsn)},
            )
        except Exception as exc:
            return StoreHealth(
                backend="postgres",
                ok=False,
                schema_version=None,
                details={"error": str(exc), "dsn": _redact_dsn(self.dsn)},
            )

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.db.connect() as con:
            return con.execute(sql, params).fetchall()

    def execute_write(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        with self.db.connect() as con:
            cur = con.execute(sql, params)
            con.commit()
            return int(cur.rowcount or 0)

    @contextmanager
    def transaction(self) -> Iterator[Any]:
        with self.db.connect() as con:
            try:
                yield con
                con.commit()
            except Exception:
                con.rollback()
                raise
