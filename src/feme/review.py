from __future__ import annotations

from .db import Database, rows_to_dicts
from .utils import json_dumps, json_loads, new_id, now_iso

VALID_ACTIONS = {
    "accept",
    "reject",
    "verify",
    "archive",
    "dispute",
    "supersede",
    "restore",
}
VALID_EVIDENCE_ACTIONS = {"approve", "reject"}
STATUS_BY_ACTION = {
    "accept": "active",
    "verify": "active",
    "reject": "rejected",
    "archive": "archived",
    "dispute": "disputed",
    "supersede": "superseded",
    "restore": "active",
}
EVIDENCE_STATUS_BY_ACTION = {
    "approve": "active",
    "reject": "rejected",
}


class ReviewQueue:
    def __init__(self, db: Database):
        self.db = db

    def list_pending(
        self,
        *,
        project_id: str = "default",
        limit: int = 50,
        status: str = "pending_review",
    ) -> list[dict]:
        with self.db.connect() as con:
            rows = con.execute(
                """
                SELECT c.*, COUNT(l.id) AS support_count
                FROM memory_claims c
                LEFT JOIN claim_evidence_links l ON l.claim_id = c.id
                WHERE c.project_id = ? AND c.status = ?
                GROUP BY c.id
                ORDER BY c.created_at DESC
                LIMIT ?
                """,
                (project_id, status, limit),
            ).fetchall()
        return rows_to_dicts(rows)

    def act(
        self,
        claim_id: str,
        action: str,
        *,
        reviewer: str | None = None,
        reason: str = "",
        metadata: dict | None = None,
    ) -> dict:
        if action not in VALID_ACTIONS:
            raise ValueError(f"unsupported review action: {action}")
        now = now_iso()
        metadata = metadata or {}
        with self.db.connect() as con:
            row = con.execute(
                "SELECT * FROM memory_claims WHERE id = ?", (claim_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"claim not found: {claim_id}")
            before = row["status"]
            after = STATUS_BY_ACTION[action]
            new_confidence = row["confidence"]
            if action == "verify":
                new_confidence = min(1.0, float(new_confidence) + 0.18)
                metadata = {**metadata, "user_verified": True}
            elif action == "reject":
                new_confidence = min(float(new_confidence), 0.2)
            con.execute(
                """
                UPDATE memory_claims
                SET status = ?, confidence = ?, updated_at = ?, last_touched = ?
                WHERE id = ?
                """,
                (after, new_confidence, now, now, claim_id),
            )
            con.execute(
                """
                INSERT INTO review_actions
                (id, claim_id, action, reviewer, before_status, after_status, reason, created_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id("review"),
                    claim_id,
                    action,
                    reviewer,
                    before,
                    after,
                    reason,
                    now,
                    json_dumps(metadata),
                ),
            )
            con.execute(
                """
                INSERT INTO lifecycle_events
                (id, claim_id, event_type, before_json, after_json, reason, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id("life"),
                    claim_id,
                    f"review_{action}",
                    json_dumps(dict(row)),
                    json_dumps({"status": after, "confidence": new_confidence}),
                    reason,
                    now,
                ),
            )
            con.commit()
        return {
            "claim_id": claim_id,
            "action": action,
            "before_status": before,
            "after_status": after,
            "confidence": new_confidence,
        }

    def history(self, claim_id: str) -> list[dict]:
        with self.db.connect() as con:
            rows = con.execute(
                "SELECT * FROM review_actions WHERE claim_id = ? ORDER BY created_at DESC",
                (claim_id,),
            ).fetchall()
        return rows_to_dicts(rows)

    def review_evidence(
        self,
        evidence_id: str,
        action: str,
        *,
        reviewer: str | None = None,
        reason: str = "",
        metadata: dict | None = None,
    ) -> dict:
        if action not in VALID_EVIDENCE_ACTIONS:
            raise ValueError(f"unsupported evidence review action: {action}")
        metadata = metadata or {}
        now = now_iso()
        with self.db.connect() as con:
            row = con.execute(
                "SELECT id, review_status, project_id FROM evidence_sources WHERE id = ?",
                (evidence_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"evidence not found: {evidence_id}")
            before = row["review_status"]
            after = EVIDENCE_STATUS_BY_ACTION[action]
            existing_metadata = json_loads(
                con.execute(
                    "SELECT metadata_json FROM evidence_sources WHERE id = ?",
                    (evidence_id,),
                ).fetchone()["metadata_json"],
                default={},
            )
            con.execute(
                """
                UPDATE evidence_sources
                SET review_status = ?, metadata_json = ?
                WHERE id = ?
                """,
                (
                    after,
                    json_dumps(
                        {
                            **existing_metadata,
                            "reviewed_at": now,
                            "review_action": action,
                            **metadata,
                        }
                    ),
                    evidence_id,
                ),
            )
            con.execute(
                """
                INSERT INTO review_actions
                (id, claim_id, action, reviewer, before_status, after_status, reason, created_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id("review"),
                    None,
                    f"evidence_{action}",
                    reviewer,
                    before,
                    after,
                    reason,
                    now,
                    json_dumps({**metadata, "evidence_id": evidence_id}),
                ),
            )
            con.commit()
        return {
            "evidence_id": evidence_id,
            "action": action,
            "before_status": before,
            "after_status": after,
        }
