from __future__ import annotations

from .db import Database, rows_to_dicts
from .utils import json_dumps, new_id, now_iso


class ProjectManager:
    def __init__(self, db: Database):
        self.db = db

    def ensure(self, project_id: str, *, name: str | None = None, description: str | None = None) -> dict:
        now = now_iso()
        with self.db.connect() as con:
            row = con.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            if row:
                return dict(row)
            con.execute(
                "INSERT INTO projects (id, name, description, created_at, updated_at, metadata_json) VALUES (?, ?, ?, ?, ?, ?)",
                (project_id, name or project_id, description, now, now, json_dumps({})),
            )
            con.commit()
        return {"id": project_id, "name": name or project_id, "description": description, "created_at": now, "updated_at": now, "metadata_json": "{}"}

    def list(self) -> list[dict]:
        with self.db.connect() as con:
            rows = con.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
        return rows_to_dicts(rows)

    def stats(self, project_id: str = "default") -> dict:
        with self.db.connect() as con:
            evidence = con.execute("SELECT COUNT(*) AS n FROM evidence_sources WHERE project_id = ?", (project_id,)).fetchone()["n"]
            claims_by_status = rows_to_dicts(con.execute("SELECT status, COUNT(*) AS n FROM memory_claims WHERE project_id = ? GROUP BY status", (project_id,)).fetchall())
            chunks = con.execute(
                """SELECT COUNT(*) AS n FROM text_chunks tc JOIN evidence_sources e ON e.id = tc.evidence_id WHERE e.project_id = ?""",
                (project_id,),
            ).fetchone()["n"]
            contradictions = con.execute(
                """
                SELECT COUNT(*) AS n FROM memory_contradictions x
                JOIN memory_claims a ON a.id = x.claim_a_id
                WHERE a.project_id = ? AND x.status = 'unresolved'
                """,
                (project_id,),
            ).fetchone()["n"]
        return {"project_id": project_id, "evidence_sources": evidence, "chunks": chunks, "claims_by_status": claims_by_status, "unresolved_contradictions": contradictions}
