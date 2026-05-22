from __future__ import annotations

import json

from .db import Database
from .embeddings import HashingEmbedder
from .utils import new_id, now_iso


class MaintenanceManager:
    def __init__(self, db: Database):
        self.db = db
        self.embedder = HashingEmbedder()

    def rebuild_fts(self, *, project_id: str = "default") -> dict:
        with self.db.connect() as con:
            if str(getattr(self.db, "backend", "sqlite")).lower() == "postgres":
                claim_count = con.execute("SELECT COUNT(*) AS n FROM memory_claims WHERE project_id = ?", (project_id,)).fetchone()["n"]
                chunk_count = con.execute(
                    """
                    SELECT COUNT(*) AS n
                    FROM text_chunks tc
                    JOIN evidence_sources es ON es.id = tc.evidence_id
                    WHERE es.project_id = ?
                    """,
                    (project_id,),
                ).fetchone()["n"]
                # Native Postgres FTS vectors are generated columns. ANALYZE refreshes planner stats.
                con.execute("ANALYZE memory_claims")
                con.execute("ANALYZE text_chunks")
                con.commit()
                return {"project_id": project_id, "claims_indexed": int(claim_count), "chunks_indexed": int(chunk_count), "backend": "postgres"}
            rows = con.execute(
                """
                SELECT tc.id, tc.evidence_id, tc.text
                FROM text_chunks tc
                JOIN evidence_sources es ON es.id = tc.evidence_id
                WHERE es.project_id = ?
                """,
                (project_id,),
            ).fetchall()
            for row in rows:
                con.execute("DELETE FROM text_chunks_fts WHERE chunk_id = ?", (row["id"],))
                con.execute("INSERT INTO text_chunks_fts (chunk_id, evidence_id, text) VALUES (?, ?, ?)", (row["id"], row["evidence_id"], row["text"]))
            con.commit()
        return {"project_id": project_id, "chunks_indexed": len(rows), "backend": "sqlite"}

    def rebuild_embeddings(self, *, project_id: str = "default", owner_type: str = "chunk") -> dict:
        now = now_iso()
        count = 0
        with self.db.connect() as con:
            if owner_type == "chunk":
                rows = con.execute(
                    """
                    SELECT tc.id, tc.text
                    FROM text_chunks tc
                    JOIN evidence_sources es ON es.id = tc.evidence_id
                    WHERE es.project_id = ?
                    """,
                    (project_id,),
                ).fetchall()
                for row in rows:
                    con.execute("DELETE FROM embeddings WHERE owner_type = 'chunk' AND owner_id = ?", (row["id"],))
                    con.execute(
                        "INSERT INTO embeddings (id, owner_type, owner_id, vector_json, model, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (new_id("emb"), "chunk", row["id"], json.dumps(self.embedder.embed(row["text"])), "hashing-embedding-v1", now),
                    )
                    count += 1
            elif owner_type == "claim":
                rows = con.execute("SELECT id, claim_text FROM memory_claims WHERE project_id = ?", (project_id,)).fetchall()
                for row in rows:
                    con.execute("DELETE FROM embeddings WHERE owner_type = 'claim' AND owner_id = ?", (row["id"],))
                    con.execute(
                        "INSERT INTO embeddings (id, owner_type, owner_id, vector_json, model, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (new_id("emb"), "claim", row["id"], json.dumps(self.embedder.embed(row["claim_text"])), "hashing-embedding-v1", now),
                    )
                    count += 1
            else:
                raise ValueError("owner_type must be 'chunk' or 'claim'")
            con.commit()
        return {"project_id": project_id, "owner_type": owner_type, "embeddings_rebuilt": count}

    def vacuum(self) -> dict:
        with self.db.connect() as con:
            con.execute("VACUUM")
        return {"vacuumed": True}
