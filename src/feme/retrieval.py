from __future__ import annotations

import json
from typing import Any

from .db import Database
from .embeddings import HashingEmbedder, cosine
from .models import RetrievalResult
from .rerank import diversify_results
from .scoring import retrieval_score
from .utils import json_dumps, new_id, now_iso


class RetrievalPlanner:
    def __init__(self, db: Database):
        self.db = db
        self.embedder = HashingEmbedder()

    def search(
        self,
        query: str,
        *,
        project_id: str = "default",
        top_k: int = 10,
        include_statuses: tuple[str, ...] | None = None,
        include_pending_review: bool = True,
    ) -> list[RetrievalResult]:
        if include_statuses is None:
            include_statuses = (
                ("active", "pending_review", "disputed")
                if include_pending_review
                else ("active", "disputed")
            )
        claim_results = self._search_claims(
            query,
            project_id=project_id,
            top_k=top_k * 2,
            include_statuses=include_statuses,
        )
        include_review_statuses = (
            ("active", "pending_review")
            if "pending_review" in include_statuses
            else ("active",)
        )
        chunk_results = self._search_chunks(
            query,
            project_id=project_id,
            top_k=top_k * 2,
            include_review_statuses=include_review_statuses,
        )
        merged_raw = _dedupe_results(
            sorted(claim_results + chunk_results, key=lambda r: r.score, reverse=True)
        )
        merged = diversify_results(query, merged_raw, top_k=top_k)
        self._audit(
            query,
            merged,
            project_id=project_id,
            include_statuses=include_statuses,
            include_pending_review=include_pending_review,
        )
        self._touch_claims([r.claim_id for r in merged if r.claim_id])
        return merged

    def _search_claims(
        self,
        query: str,
        *,
        project_id: str,
        top_k: int,
        include_statuses: tuple[str, ...],
    ) -> list[RetrievalResult]:
        qvec = self.embedder.embed(query)
        placeholders = ",".join("?" for _ in include_statuses)
        backend = "postgres" if _is_postgres(self.db) else "sqlite"
        search_mode = "lexical_fallback"
        with self.db.connect() as con:
            fts_rows = []
            if _is_postgres(self.db):
                try:
                    fts_rows = con.execute(
                        f"""
                        SELECT c.id, ts_rank_cd(c.claim_tsv, websearch_to_tsquery('english', ?)) AS pg_rank
                        FROM memory_claims c
                        WHERE c.project_id = ?
                          AND c.status IN ({placeholders})
                          AND c.claim_tsv @@ websearch_to_tsquery('english', ?)
                        ORDER BY pg_rank DESC
                        LIMIT ?
                        """,
                        (query, project_id, *include_statuses, query, top_k),
                    ).fetchall()
                    search_mode = "postgres_fts"
                except Exception:
                    fts_rows = []
            else:
                try:
                    fts_rows = con.execute(
                        """
                        SELECT c.*, bm25(memory_claims_fts) AS bm25_score
                        FROM memory_claims_fts
                        JOIN memory_claims c ON c.id = memory_claims_fts.claim_id
                        WHERE memory_claims_fts MATCH ? AND c.project_id = ?
                        LIMIT ?
                        """,
                        (_fts_query(query), project_id, top_k),
                    ).fetchall()
                    search_mode = "sqlite_fts"
                except Exception:
                    fts_rows = []
            all_rows = con.execute(
                f"""
                SELECT c.*, e.vector_json
                FROM memory_claims c
                LEFT JOIN embeddings e ON e.owner_type = 'claim' AND e.owner_id = c.id
                WHERE c.project_id = ? AND c.status IN ({placeholders})
                LIMIT 1000
                """,
                (project_id, *include_statuses),
            ).fetchall()
            contradictions = {
                row["claim_a_id"]
                for row in con.execute(
                    "SELECT claim_a_id FROM memory_contradictions WHERE status = 'unresolved'"
                )
            } | {
                row["claim_b_id"]
                for row in con.execute(
                    "SELECT claim_b_id FROM memory_contradictions WHERE status = 'unresolved'"
                )
            }
            support_counts = {
                row["claim_id"]: row["n"]
                for row in con.execute(
                    "SELECT claim_id, COUNT(*) AS n FROM claim_evidence_links GROUP BY claim_id"
                )
            }
        if _is_postgres(self.db):
            keyword_ids = {
                r["id"]: max(0.0, min(1.0, float(r["pg_rank"]))) for r in fts_rows
            }
        else:
            keyword_ids = {
                r["id"]: max(0.0, 1.0 / (1.0 + abs(float(r["bm25_score"]))))
                for r in fts_rows
            }
        out: list[RetrievalResult] = []
        for row in all_rows:
            vec = _parse_vector(
                row.get("vector_json") if isinstance(row, dict) else row["vector_json"]
            )
            sem = cosine(qvec, vec)
            kw = max(
                keyword_ids.get(row["id"], 0.0),
                _lexical_score(query, row["claim_text"]),
            )
            contradiction_penalty = 0.20 if row["id"] in contradictions else 0.0
            stale_penalty = (
                0.20
                if row["status"] in {"stale", "superseded", "archived", "rejected"}
                else 0.0
            )
            unsupported_penalty = (
                0.12 if int(support_counts.get(row["id"], 0)) == 0 else 0.0
            )
            score = retrieval_score(
                semantic_similarity=sem,
                keyword_score=kw,
                source_quality=float(row["source_quality"]),
                confidence=float(row["confidence"]),
                task_relevance=max(sem, kw),
                salience=float(row["salience"]),
                recency=0.5,
                contradiction_penalty=contradiction_penalty,
                stale_penalty=stale_penalty,
                unsupported_ai_summary_penalty=unsupported_penalty,
            )
            if score > 0.10:
                span_ids = self._span_ids_for_claim(row["id"])
                out.append(
                    RetrievalResult(
                        kind="claim",
                        id=row["id"],
                        claim_id=row["id"],
                        text=row["claim_text"],
                        score=score,
                        span_ids=span_ids,
                        metadata={
                            "subject": row["subject"],
                            "predicate": row["predicate"],
                            "object": row["object"],
                            "status": row["status"],
                            "confidence": row["confidence"],
                            "source_quality": row["source_quality"],
                            "support_count": support_counts.get(row["id"], 0),
                            "backend": backend,
                            "search_mode": search_mode,
                        },
                    )
                )
        return sorted(out, key=lambda r: r.score, reverse=True)[:top_k]

    def _search_chunks(
        self,
        query: str,
        *,
        project_id: str,
        top_k: int,
        include_review_statuses: tuple[str, ...] = ("active", "pending_review"),
    ) -> list[RetrievalResult]:
        qvec = self.embedder.embed(query)
        backend = "postgres" if _is_postgres(self.db) else "sqlite"
        search_mode = "lexical_fallback"
        placeholders = ",".join("?" for _ in include_review_statuses)
        with self.db.connect() as con:
            fts_rows = []
            if _is_postgres(self.db):
                try:
                    fts_rows = con.execute(
                        f"""
                        SELECT tc.id, ts_rank_cd(tc.chunk_tsv, websearch_to_tsquery('english', ?)) AS pg_rank
                        FROM text_chunks tc
                        JOIN evidence_sources es ON es.id = tc.evidence_id
                        WHERE es.project_id = ?
                          AND es.review_status IN ({placeholders})
                          AND tc.chunk_tsv @@ websearch_to_tsquery('english', ?)
                        ORDER BY pg_rank DESC
                        LIMIT ?
                        """,
                        (query, project_id, *include_review_statuses, query, top_k),
                    ).fetchall()
                    search_mode = "postgres_fts"
                except Exception:
                    fts_rows = []
            else:
                try:
                    fts_rows = con.execute(
                        f"""
                        SELECT tc.*, es.project_id, bm25(text_chunks_fts) AS bm25_score
                        FROM text_chunks_fts
                        JOIN text_chunks tc ON tc.id = text_chunks_fts.chunk_id
                        JOIN evidence_sources es ON es.id = tc.evidence_id
                        WHERE text_chunks_fts MATCH ?
                          AND es.project_id = ?
                          AND es.review_status IN ({placeholders})
                        LIMIT ?
                        """,
                        (
                            _fts_query(query),
                            project_id,
                            *include_review_statuses,
                            top_k,
                        ),
                    ).fetchall()
                    search_mode = "sqlite_fts"
                except Exception:
                    fts_rows = []
            all_rows = con.execute(
                f"""
                SELECT tc.*, e.vector_json, es.project_id, es.source_type, es.title
                FROM text_chunks tc
                JOIN evidence_sources es ON es.id = tc.evidence_id
                LEFT JOIN embeddings e ON e.owner_type = 'chunk' AND e.owner_id = tc.id
                WHERE es.project_id = ?
                  AND es.review_status IN ({placeholders})
                LIMIT 1000
                """,
                (project_id, *include_review_statuses),
            ).fetchall()
        if _is_postgres(self.db):
            keyword_ids = {
                r["id"]: max(0.0, min(1.0, float(r["pg_rank"]))) for r in fts_rows
            }
        else:
            keyword_ids = {
                r["id"]: max(0.0, 1.0 / (1.0 + abs(float(r["bm25_score"]))))
                for r in fts_rows
            }
        out: list[RetrievalResult] = []
        for row in all_rows:
            vec = _parse_vector(
                row.get("vector_json") if isinstance(row, dict) else row["vector_json"]
            )
            sem = cosine(qvec, vec)
            kw = max(
                keyword_ids.get(row["id"], 0.0), _lexical_score(query, row["text"])
            )
            score = retrieval_score(
                semantic_similarity=sem,
                keyword_score=kw,
                source_quality=float(row["source_quality"]),
                confidence=0.6,
                task_relevance=max(sem, kw),
                salience=float(row["salience"]),
                recency=0.5,
            )
            if score > 0.12:
                span_ids = self._span_ids_for_chunk(row["id"])
                out.append(
                    RetrievalResult(
                        kind="chunk",
                        id=row["id"],
                        chunk_id=row["id"],
                        evidence_id=row["evidence_id"],
                        text=row["text"],
                        score=score,
                        span_ids=span_ids,
                        metadata={
                            "token_count": row["token_count"],
                            "source_quality": row["source_quality"],
                            "source_type": row["source_type"],
                            "title": row["title"],
                            "backend": backend,
                            "search_mode": search_mode,
                        },
                    )
                )
        return sorted(out, key=lambda r: r.score, reverse=True)[:top_k]

    def _span_ids_for_claim(self, claim_id: str) -> list[str]:
        with self.db.connect() as con:
            rows = con.execute(
                "SELECT span_id FROM claim_evidence_links WHERE claim_id = ? AND span_id IS NOT NULL",
                (claim_id,),
            ).fetchall()
        return [r["span_id"] for r in rows]

    def _span_ids_for_chunk(self, chunk_id: str) -> list[str]:
        with self.db.connect() as con:
            rows = con.execute(
                "SELECT id FROM token_spans WHERE chunk_id = ?", (chunk_id,)
            ).fetchall()
        return [r["id"] for r in rows]

    def _audit(
        self, query: str, results: list[RetrievalResult], **filters: object
    ) -> None:
        with self.db.connect() as con:
            con.execute(
                "INSERT INTO retrieval_events (id, query, filters_json, selected_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    new_id("ret"),
                    query,
                    json_dumps(filters),
                    json_dumps([r.model_dump() for r in results]),
                    now_iso(),
                ),
            )
            con.commit()

    def _touch_claims(self, claim_ids: list[str]) -> None:
        if not claim_ids:
            return
        now = now_iso()
        with self.db.connect() as con:
            for claim_id in claim_ids:
                con.execute(
                    """
                    UPDATE memory_claims
                    SET salience = MIN(1.0, salience + 0.02), last_touched = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (now, now, claim_id),
                )
            con.commit()


def _dedupe_results(results: list[RetrievalResult]) -> list[RetrievalResult]:
    seen: set[tuple[str, str]] = set()
    out: list[RetrievalResult] = []
    for r in results:
        key = (r.kind, r.id)
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _fts_query(query: str) -> str:
    terms = [t for t in query.replace('"', " ").split() if t.strip()]
    if not terms:
        return '""'
    clean = []
    for term in terms[:12]:
        term = "".join(ch for ch in term if ch.isalnum() or ch == "_")
        if term:
            clean.append(term)
    return " OR ".join(clean) if clean else '""'


def _parse_vector(value: Any) -> list[float]:
    if not value:
        return []
    if isinstance(value, list):
        return [float(v) for v in value]
    if isinstance(value, str):
        try:
            return [float(v) for v in json.loads(value or "[]")]
        except Exception:
            return []
    return []


def _lexical_score(query: str, text: str | None) -> float:
    if not text:
        return 0.0
    q_terms = {t.lower() for t in query.split() if len(t.strip()) > 2}
    if not q_terms:
        return 0.0
    hay = text.lower()
    hits = sum(1 for term in q_terms if term in hay)
    return min(1.0, hits / max(1, len(q_terms)))


def _is_postgres(db: Database) -> bool:
    return str(getattr(db, "backend", "sqlite")).lower() == "postgres"
