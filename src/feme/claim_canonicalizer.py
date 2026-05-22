from __future__ import annotations

import json
from contextlib import nullcontext

from .db import Database
from .utils import json_dumps, new_id, normalize_key, now_iso


class ClaimCanonicalizer:
    """Create stable claim clusters for duplicate and near-duplicate reasoning.

    v0.5 keeps this deterministic. It groups by normalized subject/predicate and
    chooses the highest confidence/source_quality claim as canonical. Later LLM
    extractors can plug into the same table without changing consumers.
    """

    def __init__(self, db: Database):
        self.db = db

    def rebuild_clusters(self, *, project_id: str = "default", min_claims: int = 1, con=None, autocommit: bool = True) -> dict:
        now = now_iso()
        con_ctx = nullcontext(con) if con is not None else self.db.connect()
        with con_ctx as active_con:
            rows = active_con.execute(
                """
                SELECT id, subject, predicate, object, claim_text, confidence, source_quality, status
                FROM memory_claims
                WHERE project_id = ? AND status NOT IN ('rejected', 'archived')
                ORDER BY subject, predicate, confidence DESC, source_quality DESC
                """,
                (project_id,),
            ).fetchall()
            groups: dict[str, list[dict]] = {}
            for row in rows:
                key = f"{normalize_key(row['subject'])}::{normalize_key(row['predicate'])}"
                groups.setdefault(key, []).append(dict(row))
            created_or_updated = 0
            for key, claims in groups.items():
                if len(claims) < min_claims:
                    continue
                canonical = sorted(claims, key=lambda c: (float(c["confidence"]), float(c["source_quality"])), reverse=True)[0]
                claim_ids = [c["id"] for c in claims]
                title = f"{canonical['subject']} / {canonical['predicate']}"
                confidence = sum(float(c["confidence"]) for c in claims) / max(1, len(claims))
                existing = active_con.execute("SELECT id FROM claim_clusters WHERE project_id = ? AND cluster_key = ?", (project_id, key)).fetchone()
                if existing:
                    active_con.execute(
                        """
                        UPDATE claim_clusters
                        SET title = ?, canonical_claim_id = ?, claim_ids_json = ?, confidence = ?, updated_at = ?, metadata_json = ?
                        WHERE id = ?
                        """,
                        (title, canonical["id"], json_dumps(claim_ids), confidence, now, json_dumps({"claim_count": len(claims)}), existing["id"]),
                    )
                else:
                    active_con.execute(
                        """
                        INSERT INTO claim_clusters
                        (id, project_id, cluster_key, title, canonical_claim_id, claim_ids_json, confidence, created_at, updated_at, metadata_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (new_id("clu"), project_id, key, title, canonical["id"], json_dumps(claim_ids), confidence, now, now, json_dumps({"claim_count": len(claims)})),
                    )
                created_or_updated += 1
            if autocommit:
                active_con.commit()
        return {"clusters_created_or_updated": created_or_updated, "project_id": project_id}

    def list_clusters(self, *, project_id: str = "default", limit: int = 100) -> list[dict]:
        with self.db.connect() as con:
            rows = con.execute(
                "SELECT * FROM claim_clusters WHERE project_id = ? ORDER BY updated_at DESC LIMIT ?",
                (project_id, limit),
            ).fetchall()
        out: list[dict] = []
        for row in rows:
            item = dict(row)
            item["claim_ids"] = json.loads(item.pop("claim_ids_json") or "[]")
            item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
            out.append(item)
        return out
