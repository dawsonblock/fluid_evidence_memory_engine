from __future__ import annotations

import json

from .db import Database
from .utils import json_dumps, new_id, now_iso, sha256_text

REDACTION_TEXT = "[REDACTED_BY_RETENTION_POLICY]"


class RetentionManager:
    def __init__(self, db: Database):
        self.db = db

    def redact_evidence(
        self, evidence_id: str, *, actor: str | None = None, reason: str = ""
    ) -> dict:
        """Redact stored text while preserving metadata and audit trail.

        This is a local data-minimization tool, not legal deletion certification.
        It replaces snapshots/chunks/spans with a redaction marker and archives
        dependent claims so they stop influencing retrieval.
        """
        now = now_iso()
        redacted_hash = sha256_text(REDACTION_TEXT)
        with self.db.connect() as con:
            evidence = con.execute(
                "SELECT * FROM evidence_sources WHERE id = ?", (evidence_id,)
            ).fetchone()
            if not evidence:
                raise KeyError(f"evidence not found: {evidence_id}")
            claim_ids = [
                r["claim_id"]
                for r in con.execute(
                    "SELECT DISTINCT claim_id FROM claim_evidence_links WHERE evidence_id = ?",
                    (evidence_id,),
                ).fetchall()
            ]
            con.execute(
                "UPDATE evidence_snapshots SET text = ?, text_sha256 = ? WHERE evidence_id = ?",
                (REDACTION_TEXT, redacted_hash, evidence_id),
            )
            con.execute(
                "UPDATE text_chunks SET text = ?, token_count = 1, salience = 0.0 WHERE evidence_id = ?",
                (REDACTION_TEXT, evidence_id),
            )
            con.execute(
                "UPDATE token_spans SET text = ?, text_sha256 = ? WHERE evidence_id = ?",
                (REDACTION_TEXT, redacted_hash, evidence_id),
            )
            con.execute(
                "DELETE FROM text_chunks_fts WHERE evidence_id = ?", (evidence_id,)
            )
            chunks = con.execute(
                "SELECT id FROM text_chunks WHERE evidence_id = ?", (evidence_id,)
            ).fetchall()
            for ch in chunks:
                con.execute(
                    "INSERT INTO text_chunks_fts (chunk_id, evidence_id, text) VALUES (?, ?, ?)",
                    (ch["id"], evidence_id, REDACTION_TEXT),
                )
            for claim_id in claim_ids:
                before = con.execute(
                    "SELECT * FROM memory_claims WHERE id = ?", (claim_id,)
                ).fetchone()
                if before:
                    con.execute(
                        "UPDATE memory_claims SET status = 'archived', salience = 0.0, updated_at = ?, last_touched = ? WHERE id = ?",
                        (now, now, claim_id),
                    )
                    con.execute(
                        "INSERT INTO lifecycle_events (id, claim_id, event_type, before_json, after_json, reason, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            new_id("life"),
                            claim_id,
                            "retention_redact_evidence",
                            json_dumps(dict(before)),
                            json_dumps({"status": "archived"}),
                            reason,
                            now,
                        ),
                    )
            try:
                old_metadata = json.loads(evidence["metadata_json"] or "{}")
            except Exception:
                old_metadata = {}
            con.execute(
                "UPDATE evidence_sources SET review_status = 'redacted', metadata_json = ? WHERE id = ?",
                (
                    json_dumps(
                        {**old_metadata, "redacted_at": now, "redaction_reason": reason}
                    ),
                    evidence_id,
                ),
            )
            con.execute(
                "INSERT INTO retention_actions (id, project_id, action, target_type, target_id, actor, reason, created_at, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_id("retention"),
                    evidence["project_id"],
                    "redact",
                    "evidence",
                    evidence_id,
                    actor,
                    reason,
                    now,
                    json_dumps({"claims_archived": claim_ids}),
                ),
            )
            con.commit()
        return {
            "evidence_id": evidence_id,
            "claims_archived": len(claim_ids),
            "redacted": True,
        }

    def archive_project_claims(
        self, *, project_id: str = "default", actor: str | None = None, reason: str = ""
    ) -> dict:
        now = now_iso()
        with self.db.connect() as con:
            rows = con.execute(
                "SELECT id FROM memory_claims WHERE project_id = ? AND status NOT IN ('archived','rejected')",
                (project_id,),
            ).fetchall()
            for row in rows:
                con.execute(
                    "UPDATE memory_claims SET status = 'archived', updated_at = ?, last_touched = ? WHERE id = ?",
                    (now, now, row["id"]),
                )
            con.execute(
                "INSERT INTO retention_actions (id, project_id, action, target_type, target_id, actor, reason, created_at, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_id("retention"),
                    project_id,
                    "archive",
                    "project_claims",
                    project_id,
                    actor,
                    reason,
                    now,
                    json_dumps({"claim_count": len(rows)}),
                ),
            )
            con.commit()
        return {"project_id": project_id, "claims_archived": len(rows)}

    def history(self, *, project_id: str = "default", limit: int = 100) -> list[dict]:
        with self.db.connect() as con:
            rows = con.execute(
                "SELECT * FROM retention_actions WHERE project_id = ? ORDER BY created_at DESC LIMIT ?",
                (project_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]
