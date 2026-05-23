from __future__ import annotations

import json
from contextlib import nullcontext
from pathlib import Path

from .chunking import chunk_text
from .db import Database
from .embeddings import HashingEmbedder
from .entity_extractor import persist_entities_for_chunk
from .evidence_vault import EvidenceVault
from .policy import MemoryPolicy
from .projects import ProjectManager
from .sensitive import find_sensitive, sensitivity_score
from .source_registry import SourceRegistry
from .temporal import TimelineManager
from .token_trace import Tokenizer
from .utils import json_dumps, new_id, now_iso, sha256_text


class EvidenceIngestor:
    def __init__(
        self,
        db: Database,
        tokenizer: Tokenizer | None = None,
        policy: MemoryPolicy | None = None,
    ):
        self.db = db
        self.tokenizer = tokenizer or Tokenizer()
        self.embedder = HashingEmbedder()
        self.policy = policy or MemoryPolicy.default()

    def ingest_text(
        self,
        text: str,
        *,
        source_type: str = "note",
        title: str | None = None,
        source_uri: str | None = None,
        project_id: str = "default",
        metadata: dict | None = None,
        max_chunk_tokens: int = 900,
        overlap_tokens: int = 120,
        extract_entities: bool = True,
        deduplicate: bool = True,
        con=None,
        autocommit: bool = True,
    ) -> dict:
        metadata = metadata or {}
        ProjectManager(self.db).ensure(project_id)
        now = now_iso()
        evidence_sha = sha256_text(text)
        evidence_id = new_id("ev")
        job_id = new_id("job")
        snapshot_id = new_id("snap")

        sensitive_findings = [f.__dict__ for f in find_sensitive(text)]
        if sensitive_findings:
            metadata = {
                **metadata,
                "sensitive_findings": sensitive_findings,
                "sensitivity_score": sensitivity_score(text),
            }

        chunks = chunk_text(text, self.tokenizer, max_chunk_tokens, overlap_tokens)
        chunk_ids: list[str] = []
        span_ids: list[str] = []
        entity_mention_ids: list[str] = []

        con_ctx = nullcontext(con) if con is not None else self.db.connect()
        with con_ctx as active_con:
            registry_row = SourceRegistry(self.db).assert_enabled(
                source_type, project_id=project_id, con=active_con, autocommit=False
            )
            if deduplicate:
                existing = active_con.execute(
                    "SELECT id FROM evidence_sources WHERE project_id = ? AND sha256 = ? ORDER BY captured_at DESC LIMIT 1",
                    (project_id, evidence_sha),
                ).fetchone()
                if existing:
                    return {
                        "evidence_id": existing["id"],
                        "duplicate": True,
                        "chunk_ids": [],
                        "span_ids": [],
                        "entity_mention_ids": [],
                    }

            active_con.execute(
                """
                INSERT INTO ingestion_jobs
                (id, project_id, source_type, source_uri, status, started_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    project_id,
                    source_type,
                    source_uri,
                    "started",
                    now,
                    json_dumps(metadata),
                ),
            )
            active_con.execute(
                """
                INSERT OR IGNORE INTO evidence_sources
                (id, project_id, source_type, title, source_uri, sha256, captured_at, review_status, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence_id,
                    project_id,
                    source_type,
                    title,
                    source_uri,
                    evidence_sha,
                    now,
                    "pending_review",
                    json_dumps(metadata),
                ),
            )
            evidence_row = active_con.execute(
                "SELECT id FROM evidence_sources WHERE project_id = ? AND sha256 = ? ORDER BY captured_at DESC, id DESC LIMIT 1",
                (project_id, evidence_sha),
            ).fetchone()
            resolved_evidence_id = evidence_row["id"] if evidence_row else evidence_id
            if resolved_evidence_id != evidence_id:
                active_con.execute(
                    "UPDATE ingestion_jobs SET status = ?, evidence_id = ?, finished_at = ? WHERE id = ?",
                    ("duplicate", resolved_evidence_id, now, job_id),
                )
                if autocommit:
                    active_con.commit()
                return {
                    "evidence_id": resolved_evidence_id,
                    "job_id": job_id,
                    "duplicate": True,
                    "chunk_ids": [],
                    "span_ids": [],
                    "entity_mention_ids": [],
                }
            active_con.execute(
                """
                INSERT INTO evidence_snapshots (id, evidence_id, text, text_sha256, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (snapshot_id, evidence_id, text, evidence_sha, now),
            )
            active_con.execute(
                "UPDATE ingestion_jobs SET status = ?, evidence_id = ?, finished_at = ? WHERE id = ?",
                ("evidence_saved", evidence_id, now, job_id),
            )

            for ch in chunks:
                chunk_id = new_id("chunk")
                span_id = new_id("span")
                chunk_ids.append(chunk_id)
                span_ids.append(span_id)
                source_quality = float(
                    registry_row.get(
                        "default_quality", self.policy.quality_for_source(source_type)
                    )
                )
                active_con.execute(
                    """
                    INSERT INTO text_chunks
                    (id, evidence_id, snapshot_id, chunk_index, char_start, char_end, token_start, token_end, text, token_count, salience, source_quality, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk_id,
                        evidence_id,
                        snapshot_id,
                        ch.chunk_index,
                        ch.char_start,
                        ch.char_end,
                        ch.token_start,
                        ch.token_end,
                        ch.text,
                        ch.token_count,
                        0.5,
                        source_quality,
                        now,
                    ),
                )
                active_con.execute(
                    "INSERT INTO text_chunks_fts (chunk_id, evidence_id, text) VALUES (?, ?, ?)",
                    (chunk_id, evidence_id, ch.text),
                )
                active_con.execute(
                    """
                    INSERT INTO token_spans
                    (id, evidence_id, chunk_id, char_start, char_end, token_start, token_end, text_sha256, text, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        span_id,
                        evidence_id,
                        chunk_id,
                        ch.char_start,
                        ch.char_end,
                        ch.token_start,
                        ch.token_end,
                        sha256_text(ch.text),
                        ch.text,
                        now,
                    ),
                )
                vector = self.embedder.embed(ch.text)
                active_con.execute(
                    "INSERT INTO embeddings (id, owner_type, owner_id, vector_json, model, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        new_id("emb"),
                        "chunk",
                        chunk_id,
                        json.dumps(vector),
                        "hashing-embedding-v1",
                        now,
                    ),
                )

            if extract_entities:
                for chunk_id, span_id, ch in zip(chunk_ids, span_ids, chunks):
                    entity_mention_ids.extend(
                        persist_entities_for_chunk(
                            self.db,
                            {
                                "id": chunk_id,
                                "evidence_id": evidence_id,
                                "char_start": ch.char_start,
                                "text": ch.text,
                            },
                            span_id=span_id,
                            con=active_con,
                            autocommit=False,
                        )
                    )

            timeline_events = TimelineManager(self.db).build_for_evidence(
                evidence_id,
                con=active_con,
                autocommit=False,
            )

            if autocommit:
                active_con.commit()
        return {
            "evidence_id": evidence_id,
            "snapshot_id": snapshot_id,
            "job_id": job_id,
            "duplicate": False,
            "sensitivity_score": metadata.get("sensitivity_score", 0.0),
            "source_review_required": bool(registry_row.get("review_required", 0)),
            "chunk_ids": chunk_ids,
            "span_ids": span_ids,
            "entity_mention_ids": entity_mention_ids,
            "timeline_event_ids": [event["id"] for event in timeline_events],
        }

    def ingest_file(
        self, path: str, *, vault_root: str | None = None, **kwargs
    ) -> dict:
        p = Path(path)
        raw = p.read_bytes()
        text = raw.decode("utf-8", errors="replace")
        file_sha = sha256_text(text)
        metadata = dict(kwargs.pop("metadata", {}) or {})
        if vault_root:
            manifest = EvidenceVault(vault_root).store_file(
                p, file_sha, metadata=metadata
            )
            metadata["vault_manifest"] = manifest
        kwargs.setdefault("title", p.name)
        kwargs.setdefault("source_uri", str(p.resolve()))
        return self.ingest_text(text, metadata=metadata, **kwargs)


def _source_quality(source_type: str) -> float:
    return MemoryPolicy.default().quality_for_source(source_type)
