from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from ..db import Database, rows_to_dicts
from .base import StoreCapabilities, StoreHealth


class SQLiteStore:
    def __init__(self, db: Database):
        self.db = db

    def capabilities(self) -> StoreCapabilities:
        return StoreCapabilities(
            backend="sqlite",
            transactions=True,
            full_text_search=True,
            vector_search=False,
            concurrent_writes=False,
            advisory_locks=False,
        )

    def health(self) -> StoreHealth:
        return StoreHealth(
            backend="sqlite",
            ok=True,
            schema_version=self.db.schema_version(),
            details={"path": self.db.path},
        )

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.db.connect() as con:
            return rows_to_dicts(con.execute(sql, params).fetchall())

    def execute_write(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        with self.db.connect() as con:
            cur = con.execute(sql, params)
            con.commit()
            return int(cur.rowcount)

    @contextmanager
    def transaction(self) -> Iterator[Any]:
        with self.db.connect() as con:
            try:
                con.execute("BEGIN IMMEDIATE")
                yield con
                con.commit()
            except Exception:
                con.rollback()
                raise
