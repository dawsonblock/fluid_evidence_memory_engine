from __future__ import annotations

import hashlib

from .db import Database, SCHEMA_VERSION
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

V10_CLAIM_SUPPORT_SPANS_SQL = """
CREATE TABLE IF NOT EXISTS claim_support_spans (
    id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL REFERENCES memory_claims(id) ON DELETE CASCADE,
    evidence_id TEXT NOT NULL REFERENCES evidence_sources(id) ON DELETE CASCADE,
    chunk_id TEXT REFERENCES text_chunks(id) ON DELETE SET NULL,
    span_id TEXT REFERENCES token_spans(id) ON DELETE SET NULL,
    support_type TEXT NOT NULL DEFAULT 'supports',
    confidence REAL NOT NULL DEFAULT 0.5,
    char_start INTEGER,
    char_end INTEGER,
    token_start INTEGER,
    token_end INTEGER,
    quote_sha256 TEXT,
    quote_text TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_support_spans_claim ON claim_support_spans(claim_id, created_at);
CREATE INDEX IF NOT EXISTS idx_support_spans_evidence ON claim_support_spans(evidence_id);
"""

V11_API_REQUEST_AUDIT_SQL = """
CREATE TABLE IF NOT EXISTS api_request_audit (
    id TEXT PRIMARY KEY,
    method TEXT NOT NULL,
    path TEXT NOT NULL,
    required_role TEXT NOT NULL,
    resolved_role TEXT,
    decision TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    principal_hash TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_api_request_audit_created ON api_request_audit(created_at);
"""

V12_SQLITE_LEDGER_IMMUTABLE_SQL = """
CREATE TRIGGER IF NOT EXISTS trg_memory_ledger_no_update
BEFORE UPDATE ON memory_ledger
BEGIN
    SELECT RAISE(ABORT, 'memory_ledger is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_memory_ledger_no_delete
BEFORE DELETE ON memory_ledger
BEGIN
    SELECT RAISE(ABORT, 'memory_ledger is append-only');
END;
"""

V13_EXTRACTOR_AUDIT_SQL = """
CREATE TABLE IF NOT EXISTS extractor_audit (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL DEFAULT 'default',
    evidence_id TEXT NOT NULL REFERENCES evidence_sources(id) ON DELETE CASCADE,
    chunk_id TEXT REFERENCES text_chunks(id) ON DELETE SET NULL,
    extractor_mode TEXT NOT NULL,
    extractor_provider TEXT NOT NULL,
    outcome TEXT NOT NULL,
    candidate_count INTEGER NOT NULL DEFAULT 0,
    detail TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_extractor_audit_created ON extractor_audit(created_at);
CREATE INDEX IF NOT EXISTS idx_extractor_audit_project ON extractor_audit(project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_extractor_audit_evidence ON extractor_audit(evidence_id, created_at);
"""

V14_EVIDENCE_RELATION_SQL = """
ALTER TABLE claim_evidence_links ADD COLUMN evidence_relation TEXT DEFAULT 'unknown';
"""

V14_POSTGRES_EVIDENCE_RELATION_SQL = """
ALTER TABLE claim_evidence_links ADD COLUMN IF NOT EXISTS evidence_relation TEXT NOT NULL DEFAULT 'unknown';
"""

V15_EMBEDDINGS_PROVIDER_COLUMNS_SQL = """
ALTER TABLE embeddings ADD COLUMN provider TEXT NOT NULL DEFAULT 'hashing';
ALTER TABLE embeddings ADD COLUMN dimensions INTEGER NOT NULL DEFAULT 256;
ALTER TABLE embeddings ADD COLUMN config_hash TEXT NOT NULL DEFAULT '';
"""

V15_POSTGRES_EMBEDDINGS_PROVIDER_COLUMNS_SQL = """
ALTER TABLE embeddings ADD COLUMN IF NOT EXISTS provider TEXT NOT NULL DEFAULT 'hashing';
ALTER TABLE embeddings ADD COLUMN IF NOT EXISTS dimensions INTEGER NOT NULL DEFAULT 256;
ALTER TABLE embeddings ADD COLUMN IF NOT EXISTS config_hash TEXT NOT NULL DEFAULT '';
"""

V16_EVIDENCE_KIND_SQL = """
ALTER TABLE claim_evidence_links ADD COLUMN evidence_kind TEXT NOT NULL DEFAULT 'unknown';
"""

V16_POSTGRES_EVIDENCE_KIND_SQL = """
ALTER TABLE claim_evidence_links ADD COLUMN IF NOT EXISTS evidence_kind TEXT NOT NULL DEFAULT 'unknown';
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

            if backend == "postgres":
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

            if self._try_executescript(con, V10_CLAIM_SUPPORT_SPANS_SQL):
                self._record_migration(
                    con,
                    migration_id="010_claim_support_spans",
                    name="v0.7.1 claim support spans",
                    checksum=hashlib.sha256(
                        V10_CLAIM_SUPPORT_SPANS_SQL.encode("utf-8")
                    ).hexdigest(),
                    applied=applied,
                )

            if self._try_executescript(con, V11_API_REQUEST_AUDIT_SQL):
                self._record_migration(
                    con,
                    migration_id="011_api_request_audit",
                    name="v0.7.1 api request auth audit",
                    checksum=hashlib.sha256(
                        V11_API_REQUEST_AUDIT_SQL.encode("utf-8")
                    ).hexdigest(),
                    applied=applied,
                )

            if backend == "sqlite" and self._try_executescript(
                con, V12_SQLITE_LEDGER_IMMUTABLE_SQL
            ):
                self._record_migration(
                    con,
                    migration_id="012_sqlite_ledger_immutable",
                    name="v0.7.2 sqlite ledger append-only trigger",
                    checksum=hashlib.sha256(
                        V12_SQLITE_LEDGER_IMMUTABLE_SQL.encode("utf-8")
                    ).hexdigest(),
                    applied=applied,
                )

            if self._try_executescript(con, V13_EXTRACTOR_AUDIT_SQL):
                self._record_migration(
                    con,
                    migration_id="013_extractor_audit",
                    name="v0.7.4 extractor audit persistence",
                    checksum=hashlib.sha256(
                        V13_EXTRACTOR_AUDIT_SQL.encode("utf-8")
                    ).hexdigest(),
                    applied=applied,
                )

            _v14_sql = (
                V14_POSTGRES_EVIDENCE_RELATION_SQL
                if backend == "postgres"
                else V14_EVIDENCE_RELATION_SQL
            )
            v14_applied = self._try_executescript(con, _v14_sql)
            if (
                not v14_applied
                and backend == "sqlite"
                and self._sqlite_column_exists(
                    con,
                    "claim_evidence_links",
                    "evidence_relation",
                )
            ):
                v14_applied = True
            if v14_applied:
                self._record_migration(
                    con,
                    migration_id="014_evidence_relation",
                    name="v0.8 evidence_relation label on claim_evidence_links",
                    checksum=hashlib.sha256(_v14_sql.encode("utf-8")).hexdigest(),
                    applied=applied,
                )

            _v15_sql = (
                V15_POSTGRES_EMBEDDINGS_PROVIDER_COLUMNS_SQL
                if backend == "postgres"
                else V15_EMBEDDINGS_PROVIDER_COLUMNS_SQL
            )
            v15_applied = self._try_executescript(con, _v15_sql)
            if not v15_applied and backend == "sqlite":
                v15_applied = all(
                    self._sqlite_column_exists(con, "embeddings", column)
                    for column in ("provider", "dimensions", "config_hash")
                )
            if v15_applied:
                self._record_migration(
                    con,
                    migration_id="015_embeddings_provider_columns",
                    name="v0.9 embeddings provider/dimensions/config_hash columns",
                    checksum=hashlib.sha256(_v15_sql.encode("utf-8")).hexdigest(),
                    applied=applied,
                )

            _v16_sql = (
                V16_POSTGRES_EVIDENCE_KIND_SQL
                if backend == "postgres"
                else V16_EVIDENCE_KIND_SQL
            )
            if backend == "sqlite":
                v16_applied = self._sqlite_column_exists(
                    con,
                    "claim_evidence_links",
                    "evidence_kind",
                )
            else:
                v16_applied = self._try_executescript(con, _v16_sql)
            if v16_applied:
                self._record_migration(
                    con,
                    migration_id="016_evidence_kind",
                    name="v0.8 evidence_kind label on claim_evidence_links",
                    checksum=hashlib.sha256(_v16_sql.encode("utf-8")).hexdigest(),
                    applied=applied,
                )

            con.execute(
                "INSERT OR REPLACE INTO schema_meta (key, value, updated_at) VALUES (?, ?, ?)",
                ("schema_version", SCHEMA_VERSION, now_iso()),
            )
            con.commit()
        return {"applied": applied, "schema_version": SCHEMA_VERSION}

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

    @staticmethod
    def _sqlite_column_exists(con, table_name: str, column_name: str) -> bool:
        try:
            rows = con.execute(f"PRAGMA table_info({table_name})").fetchall()
        except Exception:
            return False
        for row in rows:
            name = row["name"] if hasattr(row, "keys") else row[1]
            if str(name) == column_name:
                return True
        return False

    def list_applied(self) -> list[dict]:
        with self.db.connect() as con:
            rows = con.execute(
                "SELECT * FROM schema_migrations ORDER BY applied_at"
            ).fetchall()
        return [dict(r) for r in rows]
