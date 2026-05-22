from __future__ import annotations

import json
from pathlib import Path

from .db import Database
from .utils import now_iso

EXPORT_TABLES = [
    "projects",
    "integrity_reports",
    "ingestion_jobs",
    "claim_relationships",
    "review_actions",
    "evidence_sources",
    "evidence_snapshots",
    "text_chunks",
    "token_spans",
    "entities",
    "entity_mentions",
    "memory_claims",
    "claim_evidence_links",
    "memory_contradictions",
    "memory_write_audit",
    "retrieval_events",
    "answer_audit_logs",
    "lifecycle_events",
    "source_registry",
    "timeline_events",
    "citation_records",
    "memory_capsules",
    "retention_actions",
]


class ProjectExporter:
    def __init__(self, db: Database):
        self.db = db

    def export_project(self, project_id: str, out_path: str | Path) -> dict:
        out = Path(out_path)
        payload: dict[str, object] = {"project_id": project_id, "exported_at": now_iso(), "tables": {}}
        with self.db.connect() as con:
            evidence_ids = [r["id"] for r in con.execute("SELECT id FROM evidence_sources WHERE project_id = ?", (project_id,))]
            claim_ids = [r["id"] for r in con.execute("SELECT id FROM memory_claims WHERE project_id = ?", (project_id,))]
            tables = payload["tables"]  # type: ignore[index]
            tables["evidence_sources"] = [dict(r) for r in con.execute("SELECT * FROM evidence_sources WHERE project_id = ?", (project_id,))]
            if evidence_ids:
                ph = ",".join("?" for _ in evidence_ids)
                for table in ["evidence_snapshots", "text_chunks", "token_spans"]:
                    tables[table] = [dict(r) for r in con.execute(f"SELECT * FROM {table} WHERE evidence_id IN ({ph})", evidence_ids)]
                tables["entity_mentions"] = [dict(r) for r in con.execute(f"SELECT * FROM entity_mentions WHERE evidence_id IN ({ph})", evidence_ids)]
            else:
                for table in ["evidence_snapshots", "text_chunks", "token_spans", "entity_mentions"]:
                    tables[table] = []
            tables["entities"] = [dict(r) for r in con.execute("SELECT * FROM entities")]
            tables["memory_claims"] = [dict(r) for r in con.execute("SELECT * FROM memory_claims WHERE project_id = ?", (project_id,))]
            if claim_ids:
                ph = ",".join("?" for _ in claim_ids)
                tables["claim_evidence_links"] = [dict(r) for r in con.execute(f"SELECT * FROM claim_evidence_links WHERE claim_id IN ({ph})", claim_ids)]
                tables["memory_contradictions"] = [dict(r) for r in con.execute(f"SELECT * FROM memory_contradictions WHERE claim_a_id IN ({ph}) OR claim_b_id IN ({ph})", claim_ids + claim_ids)]
                tables["lifecycle_events"] = [dict(r) for r in con.execute(f"SELECT * FROM lifecycle_events WHERE claim_id IN ({ph})", claim_ids)]
            else:
                tables["claim_evidence_links"] = []
                tables["memory_contradictions"] = []
                tables["lifecycle_events"] = []
            for table in ["source_registry", "timeline_events", "citation_records", "memory_capsules", "retention_actions"]:
                try:
                    tables[table] = [dict(r) for r in con.execute(f"SELECT * FROM {table} WHERE project_id = ?", (project_id,))]
                except Exception:
                    tables[table] = []
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"path": str(out), "project_id": project_id, "table_count": len(payload["tables"])}


    def import_project(self, in_path: str | Path, *, replace: bool = False) -> dict:
        payload = json.loads(Path(in_path).read_text(encoding="utf-8"))
        tables: dict = payload.get("tables", {})
        inserted: dict[str, int] = {}
        with self.db.connect() as con:
            for table, rows in tables.items():
                if not rows:
                    inserted[table] = 0
                    continue
                if replace:
                    # Delete only rows present in this export by primary id where possible.
                    for row in rows:
                        if "id" in row:
                            con.execute(f"DELETE FROM {table} WHERE id = ?", (row["id"],))
                count = 0
                for row in rows:
                    keys = list(row.keys())
                    cols = ", ".join(keys)
                    placeholders = ", ".join("?" for _ in keys)
                    con.execute(
                        f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({placeholders})",
                        [row[k] for k in keys],
                    )
                    count += 1
                inserted[table] = count
            con.commit()
        return {"imported_from": str(in_path), "project_id": payload.get("project_id"), "inserted": inserted}
