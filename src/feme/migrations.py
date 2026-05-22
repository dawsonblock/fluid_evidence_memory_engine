from __future__ import annotations

import hashlib

from .db import Database
from .utils import now_iso

V05_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_ledger (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL DEFAULT 'default',
    event_type TEXT NOT NULL,
    actor TEXT,
    object_type TEXT NOT NULL,
    object_id TEXT,
    before_json TEXT NOT NULL DEFAULT '{}',
    after_json TEXT NOT NULL DEFAULT '{}',
    reason TEXT NOT NULL DEFAULT '',
    previous_hash TEXT,
    event_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS claim_clusters (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL DEFAULT 'default',
    cluster_key TEXT NOT NULL,
    title TEXT NOT NULL,
    canonical_claim_id TEXT REFERENCES memory_claims(id) ON DELETE SET NULL,
    claim_ids_json TEXT NOT NULL DEFAULT '[]',
    confidence REAL NOT NULL DEFAULT 0.5,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(project_id, cluster_key)
);

CREATE TABLE IF NOT EXISTS retrieval_eval_cases (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL DEFAULT 'default',
    query TEXT NOT NULL,
    expected_claim_ids_json TEXT NOT NULL DEFAULT '[]',
    expected_terms_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS retrieval_eval_suites (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL DEFAULT 'default',
    name TEXT NOT NULL,
    case_ids_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_ledger_project_created ON memory_ledger(project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_ledger_object ON memory_ledger(object_type, object_id);
CREATE INDEX IF NOT EXISTS idx_claim_clusters_project ON claim_clusters(project_id, cluster_key);
CREATE INDEX IF NOT EXISTS idx_eval_cases_project ON retrieval_eval_cases(project_id, created_at);
"""

V07_POSTGRES_NATIVE_FTS_SQL = """
ALTER TABLE memory_claims
    ADD COLUMN IF NOT EXISTS claim_tsv tsvector GENERATED ALWAYS AS (
        to_tsvector(
            'english',
            COALESCE(subject, '') || ' ' || COALESCE(predicate, '') || ' ' || COALESCE(object, '') || ' ' || COALESCE(claim_text, '')
        )
    ) STORED;

ALTER TABLE text_chunks
    ADD COLUMN IF NOT EXISTS chunk_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', COALESCE(text, ''))) STORED;

CREATE INDEX IF NOT EXISTS idx_pg_claims_tsv ON memory_claims USING GIN (claim_tsv);
CREATE INDEX IF NOT EXISTS idx_pg_chunks_tsv ON text_chunks USING GIN (chunk_tsv);
"""

V08_POSTGRES_LEDGER_IMMUTABLE_SQL = """
CREATE OR REPLACE FUNCTION feme_memory_ledger_block_mutation()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'memory_ledger is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_memory_ledger_block_mutation ON memory_ledger;

CREATE TRIGGER trg_memory_ledger_block_mutation
BEFORE UPDATE OR DELETE ON memory_ledger
FOR EACH ROW
EXECUTE FUNCTION feme_memory_ledger_block_mutation();
"""

V09_EVIDENCE_DEDUP_INDEX_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_evidence_project_sha_unique ON evidence_sources(project_id, sha256);
"""


class MigrationManager:
    def __init__(self, db: Database):
        self.db = db

    def apply_all(self) -> dict:
        applied: list[str] = []
        backend = str(getattr(self.db, "backend", "sqlite")).lower()
        with self.db.connect() as con:
            con.executescript(V05_SQL)
            self._record_migration(
                con,
                migration_id="005_runtime_hardening",
                name="v0.5 runtime hardening",
                checksum=hashlib.sha256(V05_SQL.encode("utf-8")).hexdigest(),
                applied=applied,
            )

            if backend == "postgres":
                con.executescript(V07_POSTGRES_NATIVE_FTS_SQL)
                self._record_migration(
                    con,
                    migration_id="007_postgres_native_fts",
                    name="v0.7 postgres native fts",
                    checksum=hashlib.sha256(
                        V07_POSTGRES_NATIVE_FTS_SQL.encode("utf-8")
                    ).hexdigest(),
                    applied=applied,
                )
                con.executescript(V08_POSTGRES_LEDGER_IMMUTABLE_SQL)
                self._record_migration(
                    con,
                    migration_id="008_postgres_ledger_immutable",
                    name="v0.8 postgres ledger append-only trigger",
                    checksum=hashlib.sha256(
                        V08_POSTGRES_LEDGER_IMMUTABLE_SQL.encode("utf-8")
                    ).hexdigest(),
                    applied=applied,
                )

            if self._try_executescript(con, V09_EVIDENCE_DEDUP_INDEX_SQL):
                self._record_migration(
                    con,
                    migration_id="009_evidence_dedup_unique_index",
                    name="v0.9 evidence dedup unique index",
                    checksum=hashlib.sha256(
                        V09_EVIDENCE_DEDUP_INDEX_SQL.encode("utf-8")
                    ).hexdigest(),
                    applied=applied,
                )

            con.execute(
                "INSERT OR REPLACE INTO schema_meta (key, value, updated_at) VALUES (?, ?, ?)",
                ("schema_version", "0.6.0", now_iso()),
            )
            con.commit()
        return {"applied": applied, "schema_version": "0.6.0"}

    @staticmethod
    def _record_migration(
        con, *, migration_id: str, name: str, checksum: str, applied: list[str]
    ) -> None:
        existing = con.execute(
            "SELECT id FROM schema_migrations WHERE id = ?", (migration_id,)
        ).fetchone()
        if existing:
            return
        con.execute(
            "INSERT INTO schema_migrations (id, name, checksum, applied_at) VALUES (?, ?, ?, ?)",
            (migration_id, name, checksum, now_iso()),
        )
        applied.append(migration_id)

    @staticmethod
    def _try_executescript(con, sql: str) -> bool:
        try:
            con.executescript(sql)
            return True
        except Exception:
            # Do not block startup for legacy databases that already contain
            # duplicates; ingestion still performs best-effort dedup checks.
            return False

    def list_applied(self) -> list[dict]:
        with self.db.connect() as con:
            rows = con.execute(
                "SELECT * FROM schema_migrations ORDER BY applied_at"
            ).fetchall()
        return [dict(r) for r in rows]
