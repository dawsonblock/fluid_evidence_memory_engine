from __future__ import annotations

from contextlib import nullcontext

from .db import Database, rows_to_dicts
from .utils import json_dumps, new_id, now_iso


DEFAULT_SOURCE_QUALITIES = {
    "official_record": 0.95,
    "court_record": 0.92,
    "legal_xml": 0.90,
    "government_dataset": 0.88,
    "uploaded_pdf": 0.72,
    "email": 0.65,
    "chat": 0.58,
    "note": 0.55,
    "ai_generated": 0.25,
}


class SourceRegistry:
    """Project-scoped source allowlist/quality registry.

    The registry prevents accidental ingestion from disabled source classes and lets
    legal/evidence projects weight official sources above notes or AI output.
    """

    def __init__(self, db: Database):
        self.db = db

    def ensure_defaults(self, *, project_id: str = "default", con=None, autocommit: bool = True) -> int:
        now = now_iso()
        inserted = 0
        con_ctx = nullcontext(con) if con is not None else self.db.connect()
        with con_ctx as active_con:
            for source_type, quality in DEFAULT_SOURCE_QUALITIES.items():
                before = active_con.total_changes
                active_con.execute(
                    """
                    INSERT OR IGNORE INTO source_registry
                    (id, project_id, source_type, enabled, default_quality, review_required, created_at, updated_at, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        new_id("src"),
                        project_id,
                        source_type,
                        1,
                        quality,
                        1 if source_type in {"ai_generated", "chat", "note"} else 0,
                        now,
                        now,
                        "{}",
                    ),
                )
                if active_con.total_changes > before:
                    inserted += 1
            if autocommit:
                active_con.commit()
        return inserted

    def upsert(
        self,
        source_type: str,
        *,
        project_id: str = "default",
        enabled: bool = True,
        default_quality: float | None = None,
        review_required: bool | None = None,
        metadata: dict | None = None,
        con=None,
        autocommit: bool = True,
    ) -> dict:
        now = now_iso()
        default_quality = DEFAULT_SOURCE_QUALITIES.get(source_type, 0.5) if default_quality is None else float(default_quality)
        review_required = source_type in {"ai_generated", "note"} if review_required is None else bool(review_required)
        metadata = metadata or {}
        con_ctx = nullcontext(con) if con is not None else self.db.connect()
        with con_ctx as active_con:
            existing = active_con.execute(
                "SELECT * FROM source_registry WHERE project_id = ? AND source_type = ?",
                (project_id, source_type),
            ).fetchone()
            if existing:
                active_con.execute(
                    """
                    UPDATE source_registry
                    SET enabled = ?, default_quality = ?, review_required = ?, updated_at = ?, metadata_json = ?
                    WHERE id = ?
                    """,
                    (int(enabled), default_quality, int(review_required), now, json_dumps(metadata), existing["id"]),
                )
                source_id = existing["id"]
            else:
                source_id = new_id("src")
                active_con.execute(
                    """
                    INSERT INTO source_registry
                    (id, project_id, source_type, enabled, default_quality, review_required, created_at, updated_at, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (source_id, project_id, source_type, int(enabled), default_quality, int(review_required), now, now, json_dumps(metadata)),
                )
            if autocommit:
                active_con.commit()
            row = active_con.execute(
                "SELECT * FROM source_registry WHERE project_id = ? AND source_type = ?",
                (project_id, source_type),
            ).fetchone()
        return dict(row) if row else {"id": source_id, "source_type": source_type}

    def set_enabled(self, source_type: str, enabled: bool, *, project_id: str = "default") -> dict:
        row = self.get(source_type, project_id=project_id)
        return self.upsert(
            source_type,
            project_id=project_id,
            enabled=enabled,
            default_quality=float(row["default_quality"]) if row else None,
            review_required=bool(row["review_required"]) if row else None,
            metadata={},
        )

    def get(self, source_type: str, *, project_id: str = "default", con=None) -> dict | None:
        con_ctx = nullcontext(con) if con is not None else self.db.connect()
        with con_ctx as active_con:
            row = active_con.execute(
                "SELECT * FROM source_registry WHERE project_id = ? AND source_type = ?",
                (project_id, source_type),
            ).fetchone()
        return dict(row) if row else None

    def list(self, *, project_id: str = "default") -> list[dict]:
        with self.db.connect() as con:
            rows = con.execute(
                "SELECT * FROM source_registry WHERE project_id = ? ORDER BY source_type",
                (project_id,),
            ).fetchall()
        return rows_to_dicts(rows)

    def assert_enabled(self, source_type: str, *, project_id: str = "default", con=None, autocommit: bool = True) -> dict:
        self.ensure_defaults(project_id=project_id, con=con, autocommit=autocommit)
        row = self.get(source_type, project_id=project_id, con=con)
        if row is None:
            row = self.upsert(source_type, project_id=project_id, con=con, autocommit=autocommit)
        if not bool(row["enabled"]):
            raise ValueError(f"source type disabled for project {project_id}: {source_type}")
        return row

    def effective_quality(self, source_type: str, *, project_id: str = "default", fallback: float = 0.5) -> float:
        row = self.get(source_type, project_id=project_id)
        if not row:
            return DEFAULT_SOURCE_QUALITIES.get(source_type, fallback)
        return float(row["default_quality"])
