from __future__ import annotations

import json
from collections import Counter

from .db import Database
from .utils import json_dumps, new_id, now_iso, sha256_text


class IntegrityChecker:
    def __init__(self, db: Database):
        self.db = db

    def run(self, *, project_id: str = "default", persist: bool = True) -> dict:
        issues: list[dict] = []
        with self.db.connect() as con:
            snapshots = con.execute(
                """
                SELECT s.*, e.project_id FROM evidence_snapshots s
                JOIN evidence_sources e ON e.id = s.evidence_id
                WHERE e.project_id = ?
                """,
                (project_id,),
            ).fetchall()
            for row in snapshots:
                actual = sha256_text(row["text"])
                if actual != row["text_sha256"]:
                    issues.append({"type": "snapshot_hash_mismatch", "evidence_id": row["evidence_id"], "snapshot_id": row["id"]})

            spans = con.execute(
                """
                SELECT ts.*, tc.text AS chunk_text, e.project_id FROM token_spans ts
                JOIN text_chunks tc ON tc.id = ts.chunk_id
                JOIN evidence_sources e ON e.id = ts.evidence_id
                WHERE e.project_id = ?
                """,
                (project_id,),
            ).fetchall()
            for row in spans:
                if row["text_sha256"] != sha256_text(row["text"]):
                    issues.append({"type": "span_hash_mismatch", "span_id": row["id"], "chunk_id": row["chunk_id"]})
                if row["text"] not in row["chunk_text"] and row["chunk_text"] not in row["text"]:
                    issues.append({"type": "span_chunk_text_mismatch", "span_id": row["id"], "chunk_id": row["chunk_id"]})

            unsupported = con.execute(
                """
                SELECT c.id, c.claim_text FROM memory_claims c
                LEFT JOIN claim_evidence_links l ON l.claim_id = c.id
                WHERE c.project_id = ? AND c.status IN ('active','pending_review','disputed')
                GROUP BY c.id HAVING COUNT(l.id) = 0
                """,
                (project_id,),
            ).fetchall()
            for row in unsupported:
                issues.append({"type": "unsupported_claim", "claim_id": row["id"], "claim_text": row["claim_text"][:160]})

            missing_embeddings = con.execute(
                """
                SELECT c.id FROM memory_claims c
                LEFT JOIN embeddings e ON e.owner_type = 'claim' AND e.owner_id = c.id
                WHERE c.project_id = ? AND e.id IS NULL
                """,
                (project_id,),
            ).fetchall()
            for row in missing_embeddings:
                issues.append({"type": "missing_claim_embedding", "claim_id": row["id"]})

            duplicate_sources = con.execute(
                """
                SELECT sha256, COUNT(*) AS n, GROUP_CONCAT(id) AS ids
                FROM evidence_sources WHERE project_id = ?
                GROUP BY sha256 HAVING COUNT(*) > 1
                """,
                (project_id,),
            ).fetchall()
            for row in duplicate_sources:
                issues.append({"type": "duplicate_evidence_sha", "sha256": row["sha256"], "count": row["n"], "evidence_ids": row["ids"]})

            unresolved = con.execute(
                """
                SELECT mc.id, COUNT(x.id) AS n FROM memory_claims mc
                JOIN memory_contradictions x ON x.claim_a_id = mc.id OR x.claim_b_id = mc.id
                WHERE mc.project_id = ? AND x.status = 'unresolved'
                GROUP BY mc.id
                """,
                (project_id,),
            ).fetchall()
            for row in unresolved:
                issues.append({"type": "unresolved_contradiction", "claim_id": row["id"], "count": row["n"]})

            by_type = Counter(issue["type"] for issue in issues)
            report = {
                "project_id": project_id,
                "ok": not issues,
                "issue_count": len(issues),
                "issues_by_type": dict(by_type),
                "issues": issues,
                "checker": "integrity-v0.3",
                "created_at": now_iso(),
            }
            if persist:
                con.execute(
                    "INSERT INTO integrity_reports (id, project_id, ok, issue_count, report_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (new_id("integrity"), project_id, int(report["ok"]), len(issues), json_dumps(report), report["created_at"]),
                )
                con.commit()
        return report
