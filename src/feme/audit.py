from __future__ import annotations

from .db import Database, rows_to_dicts


class AuditReader:
    def __init__(self, db: Database):
        self.db = db

    def recent_writes(self, limit: int = 20) -> list[dict]:
        with self.db.connect() as con:
            rows = con.execute(
                "SELECT * FROM memory_write_audit ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return rows_to_dicts(rows)

    def recent_retrievals(self, limit: int = 20) -> list[dict]:
        with self.db.connect() as con:
            rows = con.execute(
                "SELECT * FROM retrieval_events ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return rows_to_dicts(rows)
