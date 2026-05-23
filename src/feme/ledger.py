from __future__ import annotations

import hashlib
from contextlib import nullcontext
from datetime import datetime, timedelta

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
        ledger_id = new_id("led")
        before_json = json_dumps(before or {})
        after_json = json_dumps(after or {})
        metadata_json = json_dumps(metadata or {})
        con_ctx = nullcontext(con) if con is not None else self.db.connect()
        with con_ctx as active_con:
            if str(getattr(self.db, "backend", "sqlite")).lower() == "postgres":
                # Serialize hash-chain appends per project so previous_hash cannot race under concurrent writers.
                active_con.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(?))",
                    (f"feme_memory_ledger_chain:{project_id}",),
                )
            prev = active_con.execute(
                "SELECT event_hash, created_at FROM memory_ledger WHERE project_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
                (project_id,),
            ).fetchone()
            now = now_iso()
            prev_created_at = prev["created_at"] if prev is not None else None
            if prev_created_at:
                try:
                    now_dt = datetime.fromisoformat(now)
                    prev_dt = datetime.fromisoformat(prev_created_at)
                    if now_dt <= prev_dt:
                        now = (prev_dt + timedelta(microseconds=1)).isoformat()
                except Exception:
                    # Keep append durable even if legacy timestamps cannot be parsed.
                    pass
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

    def verify_chain(self, *, project_id: str | None = None) -> dict:
        with self.db.connect() as con:
            if project_id is None:
                rows = con.execute("SELECT * FROM memory_ledger").fetchall()
            else:
                rows = con.execute(
                    "SELECT * FROM memory_ledger WHERE project_id = ?",
                    (project_id,),
                ).fetchall()

        errors: list[dict] = []
        if not rows:
            return {"ok": True, "event_count": 0, "errors": []}

        rows_by_hash: dict[str, dict] = {}
        children_by_prev: dict[str | None, list[dict]] = {}

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
            if row["event_hash"] != expected:
                errors.append({"id": row["id"], "issue": "event_hash_mismatch"})

            event_hash = row["event_hash"]
            if event_hash in rows_by_hash:
                errors.append({"id": row["id"], "issue": "duplicate_event_hash"})
            rows_by_hash[event_hash] = row

            prev_hash = row["previous_hash"]
            children_by_prev.setdefault(prev_hash, []).append(row)

        if project_id is None:
            roots = children_by_prev.get(None, [])
        else:
            roots = [
                row
                for row in rows
                if row["previous_hash"] is None
                or row["previous_hash"] not in rows_by_hash
            ]
        if len(roots) != 1:
            errors.append({"issue": "invalid_root_count", "count": len(roots)})
            return {"ok": not errors, "event_count": len(rows), "errors": errors}

        visited: set[str] = set()
        current = roots[0]
        while current is not None:
            current_hash = current["event_hash"]
            if current_hash in visited:
                errors.append({"id": current["id"], "issue": "cycle_detected"})
                break
            visited.add(current_hash)

            children = children_by_prev.get(current_hash, [])
            if len(children) > 1:
                errors.append(
                    {
                        "id": current["id"],
                        "issue": "fork_detected",
                        "child_count": len(children),
                    }
                )
                break
            current = children[0] if children else None

        if len(visited) != len(rows):
            errors.append(
                {
                    "issue": "disconnected_chain",
                    "visited": len(visited),
                    "event_count": len(rows),
                }
            )

        return {"ok": not errors, "event_count": len(rows), "errors": errors}

    @staticmethod
    def _event_hash(*parts: str) -> str:
        h = hashlib.sha256()
        for part in parts:
            h.update(part.encode("utf-8"))
            h.update(b"\x1f")
        return h.hexdigest()
