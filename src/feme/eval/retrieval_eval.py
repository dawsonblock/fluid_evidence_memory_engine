"""Retrieval evaluation harness for FEME v0.8 fixtures.

Loads JSONL fixture files where each row describes:
- project_id: str
- documents: list of {source_type, text, review_status?} to ingest
  - review_status: "active" (default after approval) | "pending_review" (held)
- queries: list of {query, expected_claim_substrings, expected_quote?,
                    public_only?, note?}
  - public_only: when True the query is run in public mode (pending_review excluded)

Returns per-fixture metrics:
- case_count: number of fixture rows processed
- query_count: total queries evaluated
- substring_hit_rate: fraction of queries where all expected_claim_substrings
  appear in at least one retrieved claim_text
- quote_hit_rate: fraction of queries (with expected_quote set) where at least
  one retrieved claim has support_quote_text matching expected_quote
- claim_found_rate: fraction of queries returning at least one result
- pending_review_leak_rate: fraction of public_only queries where a
  pending_review claim leaked into results (should always be 0.0)
- stale_claim_suppression: fraction of queries where no stale/superseded
  claims were returned (1.0 when none are found, null when not tracked)
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

from ..db import Database
from ..evidence import EvidenceIngestor
from ..retrieval import RetrievalPlanner
from ..utils import json_loads


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json_loads(line, default={})
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _db_path_for(project_id: str) -> str:
    """Return a unique temp path for the project."""
    h = hashlib.sha1(f"{project_id}-{time.time_ns()}".encode()).hexdigest()[:8]
    return f"/tmp/feme_retrieval_eval_{h}.sqlite"


def evaluate_retrieval_fixture(
    fixture_path: str,
    *,
    extractor_mode: str = "heuristic",
    top_k: int = 10,
) -> dict[str, Any]:
    """Run all retrieval cases in *fixture_path* and return aggregate metrics."""
    rows = _read_jsonl(Path(fixture_path))
    if not rows:
        return {
            "fixture_path": fixture_path,
            "case_count": 0,
            "query_count": 0,
            "substring_hit_rate": 0.0,
            "quote_hit_rate": 0.0,
            "claim_found_rate": 0.0,
            "pending_review_leak_rate": None,
            "stale_claim_suppression": None,
        }

    total_queries = 0
    substring_hits = 0
    quote_eligible = 0
    quote_hits = 0
    found_hits = 0
    public_queries = 0
    public_leaks = 0
    stale_queries = 0
    stale_suppressed = 0

    _STALE_STATUSES = {"stale", "superseded", "archived", "rejected"}

    for row in rows:
        project_id = str(row.get("project_id") or "eval_project")
        documents = row.get("documents") or []
        queries = row.get("queries") or []

        # Build a fresh isolated DB for each fixture row.
        db = Database(_db_path_for(project_id))
        db.init()

        ingestor = EvidenceIngestor(db)
        # Track evidence_ids that should be promoted to "active"
        active_evidence_ids: list[str] = []
        for doc in documents:
            text = str(doc.get("text") or "")
            source_type = str(doc.get("source_type") or "secondary_source")
            doc_review_status = doc.get("review_status", "pending_review")
            if text:
                result = ingestor.ingest_text(
                    text,
                    source_type=source_type,
                    project_id=project_id,
                )
                if doc_review_status == "active":
                    active_evidence_ids.append(result["evidence_id"])

        # Promote evidence_sources and their claims to "active" when requested
        if active_evidence_ids:
            with db.connect() as con:
                placeholders = ",".join("?" for _ in active_evidence_ids)
                con.execute(
                    f"UPDATE evidence_sources SET review_status = 'active' WHERE id IN ({placeholders})",
                    active_evidence_ids,
                )
                # memory_claims has no direct evidence_id column; join through
                # claim_evidence_links and claim_support_spans to find linked claims.
                con.execute(
                    f"""UPDATE memory_claims SET status = 'active' WHERE id IN (
                        SELECT claim_id FROM claim_evidence_links
                         WHERE evidence_id IN ({placeholders})
                        UNION
                        SELECT claim_id FROM claim_support_spans
                         WHERE evidence_id IN ({placeholders})
                    )""",
                    active_evidence_ids + active_evidence_ids,
                )
                con.commit()

        for qobj in queries:
            query_text = str(qobj.get("query") or "")
            expected_substrings: list[str] = qobj.get("expected_claim_substrings") or []
            expected_quote: str | None = qobj.get("expected_quote")
            public_only: bool = bool(qobj.get("public_only", False))

            if not query_text:
                continue

            total_queries += 1
            include_pending = not public_only

            results_objs = RetrievalPlanner(db).search(
                query_text,
                project_id=project_id,
                top_k=top_k,
                include_pending_review=include_pending,
            )
            all_claim_texts = " ".join(r.text or "" for r in results_objs).lower()
            all_quotes = [r.metadata.get("support_quote_text") or "" for r in results_objs]
            all_statuses = [str(r.metadata.get("status") or "") for r in results_objs]

            if results_objs:
                found_hits += 1

            if all(sub.lower() in all_claim_texts for sub in expected_substrings):
                substring_hits += 1

            if expected_quote is not None:
                quote_eligible += 1
                if any(q == expected_quote for q in all_quotes):
                    quote_hits += 1

            if public_only:
                public_queries += 1
                if any(s == "pending_review" for s in all_statuses):
                    public_leaks += 1

            stale_queries += 1
            if not any(s in _STALE_STATUSES for s in all_statuses):
                stale_suppressed += 1

    return {
        "fixture_path": fixture_path,
        "case_count": len(rows),
        "query_count": total_queries,
        "substring_hit_rate": substring_hits / total_queries if total_queries else 0.0,
        "quote_hit_rate": quote_hits / quote_eligible if quote_eligible else 0.0,
        "claim_found_rate": found_hits / total_queries if total_queries else 0.0,
        "pending_review_leak_rate": (
            public_leaks / public_queries if public_queries else None
        ),
        "stale_claim_suppression": (
            stale_suppressed / stale_queries if stale_queries else None
        ),
        "extractor_mode": extractor_mode,
        "top_k": top_k,
    }
