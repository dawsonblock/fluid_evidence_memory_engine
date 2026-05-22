from __future__ import annotations

from collections import defaultdict

from .db import Database, rows_to_dicts
from .utils import json_dumps, new_id, normalize_key, now_iso


class MemoryConsolidator:
    """Creates compact memory capsules without replacing source claims.

    Capsules are cached views over claims. They are not truth sources; they point
    back to the claim IDs that produced them.
    """

    def __init__(self, db: Database):
        self.db = db

    def create_subject_capsules(self, *, project_id: str = "default", min_claims: int = 2, limit_subjects: int = 50) -> dict:
        now = now_iso()
        with self.db.connect() as con:
            rows = con.execute(
                """
                SELECT id, subject, predicate, object, claim_text, confidence, salience, status
                FROM memory_claims
                WHERE project_id = ? AND status IN ('active','pending_review','disputed')
                ORDER BY subject, salience DESC, confidence DESC
                """,
                (project_id,),
            ).fetchall()
            groups: dict[str, list[dict]] = defaultdict(list)
            display_subject: dict[str, str] = {}
            for row in rows:
                key = normalize_key(row["subject"])
                groups[key].append(dict(row))
                display_subject.setdefault(key, row["subject"])
            created = 0
            for key, claims in list(groups.items())[:limit_subjects]:
                if len(claims) < min_claims:
                    continue
                claim_ids = [c["id"] for c in claims[:20]]
                capsule_text = _summarize_claims(display_subject[key], claims[:12])
                avg_confidence = sum(float(c["confidence"]) for c in claims[:20]) / min(len(claims), 20)
                capsule_id = new_id("capsule")
                con.execute(
                    """
                    INSERT INTO memory_capsules
                    (id, project_id, capsule_type, title, summary_text, claim_ids_json, confidence, created_at, updated_at, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        capsule_id,
                        project_id,
                        "subject_cluster",
                        display_subject[key],
                        capsule_text,
                        json_dumps(claim_ids),
                        avg_confidence,
                        now,
                        now,
                        json_dumps({"source": "consolidation-v0.4", "claim_count": len(claims)}),
                    ),
                )
                created += 1
            con.commit()
        return {"project_id": project_id, "capsules_created": created}

    def list_capsules(self, *, project_id: str = "default", limit: int = 100) -> list[dict]:
        with self.db.connect() as con:
            rows = con.execute(
                "SELECT * FROM memory_capsules WHERE project_id = ? ORDER BY updated_at DESC LIMIT ?",
                (project_id, limit),
            ).fetchall()
        return rows_to_dicts(rows)

    def link_near_duplicate_claims(self, *, project_id: str = "default") -> dict:
        """Cheap exact-normalized duplicate detector for review surfacing."""
        with self.db.connect() as con:
            rows = con.execute(
                "SELECT id, claim_text FROM memory_claims WHERE project_id = ? AND status NOT IN ('rejected','archived')",
                (project_id,),
            ).fetchall()
            buckets: dict[str, list[str]] = defaultdict(list)
            for row in rows:
                buckets[normalize_key(row["claim_text"])].append(row["id"])
            created = 0
            now = now_iso()
            for ids in buckets.values():
                if len(ids) < 2:
                    continue
                base = ids[0]
                for other in ids[1:]:
                    exists = con.execute(
                        "SELECT 1 FROM claim_relationships WHERE source_claim_id = ? AND target_claim_id = ? AND relationship_type = 'duplicate'",
                        (base, other),
                    ).fetchone()
                    if exists:
                        continue
                    con.execute(
                        "INSERT INTO claim_relationships (id, source_claim_id, target_claim_id, relationship_type, confidence, explanation, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (new_id("rel"), base, other, "duplicate", 0.95, "normalized claim text match", now),
                    )
                    created += 1
            con.commit()
        return {"project_id": project_id, "duplicate_relationships_created": created}


def _summarize_claims(subject: str, claims: list[dict]) -> str:
    lines = [f"Subject: {subject}"]
    for c in claims:
        lines.append(f"- [{c['status']}, conf={float(c['confidence']):.2f}] {c['claim_text']}")
    return "\n".join(lines)
