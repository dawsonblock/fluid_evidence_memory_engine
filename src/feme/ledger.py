from __future__ import annotations

import hashlib
from contextlib import nullcontext

from .db import Database
from .utils import json_dumps, new_id, now_iso


class MemoryLedger:
    """Append-only governance ledger with a simple hash chain.

    The ledger does not replace database constraints. It records material state
    transitions so audits can explain who/what changed evidence, claims,
    retention, retrieval, or ingestion state.
    """

    def __init__(self, db: Database):
        self.db = db

    def append(
        self,
        *,
        event_type: str,
        object_type: str,
        object_id: str | None = None,
        project_id: str = "default",
        actor: str | None = None,
        before: dict | None = None,
        after: dict | None = None,
        reason: str = "",
        metadata: dict | None = None,
        con=None,
        autocommit: bool = True,
    ) -> dict:
        now = now_iso()
        ledger_id = new_id("led")
        before_json = json_dumps(before or {})
        after_json = json_dumps(after or {})
        metadata_json = json_dumps(metadata or {})
        con_ctx = nullcontext(con) if con is not None else self.db.connect()
        with con_ctx as active_con:
            if str(getattr(self.db, "backend", "sqlite")).lower() == "postgres":
                # Serialize hash-chain appends so previous_hash cannot race under concurrent writers.
                active_con.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(?))",
                    ("feme_memory_ledger_chain",),
                )
            prev = active_con.execute(
                "SELECT event_hash FROM memory_ledger ORDER BY created_at DESC, id DESC LIMIT 1"
            ).fetchone()
            previous_hash = prev["event_hash"] if prev else None
            event_hash = self._event_hash(
                ledger_id,
                project_id,
                event_type,
                object_type,
                object_id or "",
                before_json,
                after_json,
                reason,
                previous_hash or "",
                now,
                metadata_json,
            )
            active_con.execute(
                """
                INSERT INTO memory_ledger
                (id, project_id, event_type, actor, object_type, object_id, before_json, after_json, reason, previous_hash, event_hash, created_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ledger_id,
                    project_id,
                    event_type,
                    actor,
                    object_type,
                    object_id,
                    before_json,
                    after_json,
                    reason,
                    previous_hash,
                    event_hash,
                    now,
                    metadata_json,
                ),
            )
            if autocommit:
                active_con.commit()
        return {
            "id": ledger_id,
            "project_id": project_id,
            "event_type": event_type,
            "object_type": object_type,
            "object_id": object_id,
            "event_hash": event_hash,
            "previous_hash": previous_hash,
        }

    def list(self, *, project_id: str = "default", limit: int = 100) -> list[dict]:
        with self.db.connect() as con:
            rows = con.execute(
                "SELECT * FROM memory_ledger WHERE project_id = ? ORDER BY created_at DESC, id DESC LIMIT ?",
                (project_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def verify_chain(self) -> dict:
        with self.db.connect() as con:
            rows = con.execute(
                "SELECT * FROM memory_ledger ORDER BY created_at ASC, id ASC"
            ).fetchall()
        previous_hash = None
        errors: list[dict] = []
        for row in rows:
            expected = self._event_hash(
                row["id"],
                row["project_id"],
                row["event_type"],
                row["object_type"],
                row["object_id"] or "",
                row["before_json"],
                row["after_json"],
                row["reason"],
                row["previous_hash"] or "",
                row["created_at"],
                row["metadata_json"],
            )
            if row["previous_hash"] != previous_hash:
                errors.append({"id": row["id"], "issue": "previous_hash_mismatch"})
            if row["event_hash"] != expected:
                errors.append({"id": row["id"], "issue": "event_hash_mismatch"})
            previous_hash = row["event_hash"]
        return {"ok": not errors, "event_count": len(rows), "errors": errors}

    @staticmethod
    def _event_hash(*parts: str) -> str:
        h = hashlib.sha256()
        for part in parts:
            h.update(part.encode("utf-8"))
            h.update(b"\x1f")
        return h.hexdigest()
