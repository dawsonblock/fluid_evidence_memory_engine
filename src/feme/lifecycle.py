from __future__ import annotations

import json
from datetime import datetime, timezone

from .db import Database
from .policy import MemoryPolicy
from .utils import clamp, json_dumps, new_id, now_iso


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class MemoryLifecycleManager:
    def __init__(self, db: Database, policy: MemoryPolicy | None = None):
        self.db = db
        self.policy = policy or MemoryPolicy.default()

    def run_decay(self, *, project_id: str = "default") -> dict:
        now = datetime.now(timezone.utc)
        changed = 0
        stale = 0
        with self.db.connect() as con:
            rows = con.execute(
                """
                SELECT * FROM memory_claims
                WHERE project_id = ? AND status IN ('active', 'pending_review')
                """,
                (project_id,),
            ).fetchall()
            for row in rows:
                before = dict(row)
                created = _parse_iso(row["created_at"]) or now
                age_days = max(0, (now - created).days)
                new_salience = clamp(float(row["salience"]) - self.policy.salience_decay_per_run)
                new_status = row["status"]
                reason = "salience_decay"
                if age_days >= self.policy.stale_after_days and new_salience <= self.policy.minimum_active_salience:
                    new_status = "stale"
                    stale += 1
                    reason = "age_and_low_salience"
                if new_salience != float(row["salience"]) or new_status != row["status"]:
                    con.execute(
                        "UPDATE memory_claims SET salience = ?, status = ?, updated_at = ? WHERE id = ?",
                        (new_salience, new_status, now_iso(), row["id"]),
                    )
                    after = {**before, "salience": new_salience, "status": new_status}
                    con.execute(
                        """
                        INSERT INTO lifecycle_events
                        (id, claim_id, event_type, before_json, after_json, reason, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            new_id("life"),
                            row["id"],
                            "decay",
                            json.dumps(before, default=str),
                            json_dumps(after),
                            reason,
                            now_iso(),
                        ),
                    )
                    changed += 1
            con.commit()
        return {"changed": changed, "marked_stale": stale, "project_id": project_id}

    def touch_claim(self, claim_id: str, *, salience_boost: float = 0.05) -> None:
        now = now_iso()
        with self.db.connect() as con:
            con.execute(
                """
                UPDATE memory_claims
                SET salience = MIN(1.0, salience + ?), last_touched = ?, updated_at = ?
                WHERE id = ?
                """,
                (salience_boost, now, now, claim_id),
            )
            con.commit()
