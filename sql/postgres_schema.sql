-- Fluid Evidence Memory Engine v0.6 PostgreSQL runtime schema.
-- This schema intentionally mirrors the SQLite runtime tables so the existing
-- governed ingestion, review, retrieval, citation, retention, and ledger paths
-- can run against PostgreSQL through PostgresDatabase. No extensions are required for the baseline runtime.

CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS evidence_sources (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL DEFAULT 'default',
    source_type TEXT NOT NULL,
    title TEXT,
    source_uri TEXT,
    sha256 TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    review_status TEXT NOT NULL DEFAULT 'pending_review',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS evidence_snapshots (
    id TEXT PRIMARY KEY,
    evidence_id TEXT NOT NULL REFERENCES evidence_sources(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    text_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS text_chunks (
    id TEXT PRIMARY KEY,
    evidence_id TEXT NOT NULL REFERENCES evidence_sources(id) ON DELETE CASCADE,
    snapshot_id TEXT NOT NULL REFERENCES evidence_snapshots(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    token_start INTEGER NOT NULL,
    token_end INTEGER NOT NULL,
    text TEXT NOT NULL,
    chunk_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', COALESCE(text, ''))) STORED,
    token_count INTEGER NOT NULL,
    salience DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    source_quality DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    created_at TEXT NOT NULL
);

-- Compatibility tables for modules that maintain SQLite FTS side tables.
-- Native Postgres retrieval uses text/trigram fallback in Python for now.
CREATE TABLE IF NOT EXISTS text_chunks_fts (
    chunk_id TEXT PRIMARY KEY,
    evidence_id TEXT NOT NULL,
    text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS token_spans (
    id TEXT PRIMARY KEY,
    evidence_id TEXT NOT NULL REFERENCES evidence_sources(id) ON DELETE CASCADE,
    chunk_id TEXT NOT NULL REFERENCES text_chunks(id) ON DELETE CASCADE,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    token_start INTEGER NOT NULL,
    token_end INTEGER NOT NULL,
    text_sha256 TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS embeddings (
    id TEXT PRIMARY KEY,
    owner_type TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    vector_json TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT 'hashing-embedding-v1',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entities (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    entity_type TEXT NOT NULL DEFAULT 'unknown',
    created_at TEXT NOT NULL,
    UNIQUE(normalized_name, entity_type)
);

CREATE TABLE IF NOT EXISTS entity_mentions (
    id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    evidence_id TEXT REFERENCES evidence_sources(id) ON DELETE CASCADE,
    chunk_id TEXT REFERENCES text_chunks(id) ON DELETE CASCADE,
    span_id TEXT REFERENCES token_spans(id) ON DELETE SET NULL,
    char_start INTEGER,
    char_end INTEGER,
    mention_text TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_claims (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL DEFAULT 'default',
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object TEXT NOT NULL,
    claim_text TEXT NOT NULL,
    claim_tsv tsvector GENERATED ALWAYS AS (
        to_tsvector(
            'english',
            COALESCE(subject, '') || ' ' || COALESCE(predicate, '') || ' ' || COALESCE(object, '') || ' ' || COALESCE(claim_text, '')
        )
    ) STORED,
    memory_type TEXT NOT NULL,
    memory_level TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    salience DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    source_quality DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    valid_from TEXT,
    valid_to TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_touched TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS memory_claims_fts (
    claim_id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object TEXT NOT NULL,
    claim_text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS claim_evidence_links (
    id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL REFERENCES memory_claims(id) ON DELETE CASCADE,
    evidence_id TEXT NOT NULL REFERENCES evidence_sources(id) ON DELETE CASCADE,
    chunk_id TEXT REFERENCES text_chunks(id) ON DELETE SET NULL,
    span_id TEXT REFERENCES token_spans(id) ON DELETE SET NULL,
    support_type TEXT NOT NULL DEFAULT 'supports',
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS claim_support_spans (
    id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL REFERENCES memory_claims(id) ON DELETE CASCADE,
    evidence_id TEXT NOT NULL REFERENCES evidence_sources(id) ON DELETE CASCADE,
    chunk_id TEXT REFERENCES text_chunks(id) ON DELETE SET NULL,
    span_id TEXT REFERENCES token_spans(id) ON DELETE SET NULL,
    support_type TEXT NOT NULL DEFAULT 'supports',
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    char_start INTEGER,
    char_end INTEGER,
    token_start INTEGER,
    token_end INTEGER,
    quote_sha256 TEXT,
    quote_text TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_contradictions (
    id TEXT PRIMARY KEY,
    claim_a_id TEXT NOT NULL REFERENCES memory_claims(id) ON DELETE CASCADE,
    claim_b_id TEXT NOT NULL REFERENCES memory_claims(id) ON DELETE CASCADE,
    contradiction_type TEXT NOT NULL,
    severity DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    status TEXT NOT NULL DEFAULT 'unresolved',
    explanation TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS retrieval_events (
    id TEXT PRIMARY KEY,
    query TEXT NOT NULL,
    filters_json TEXT NOT NULL DEFAULT '{}',
    selected_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS answer_audit_logs (
    id TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    context_packet_json TEXT NOT NULL,
    answer_text TEXT,
    warnings_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_write_audit (
    id TEXT PRIMARY KEY,
    candidate_json TEXT NOT NULL,
    decision TEXT NOT NULL,
    reason_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

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

CREATE TABLE IF NOT EXISTS lifecycle_events (
    id TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL REFERENCES memory_claims(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    before_json TEXT NOT NULL DEFAULT '{}',
    after_json TEXT NOT NULL DEFAULT '{}',
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evaluation_runs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL DEFAULT 'default',
    case_json TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS review_actions (
    id TEXT PRIMARY KEY,
    claim_id TEXT REFERENCES memory_claims(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    reviewer TEXT,
    before_status TEXT,
    after_status TEXT,
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS claim_relationships (
    id TEXT PRIMARY KEY,
    source_claim_id TEXT NOT NULL REFERENCES memory_claims(id) ON DELETE CASCADE,
    target_claim_id TEXT NOT NULL REFERENCES memory_claims(id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    explanation TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ingestion_jobs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL DEFAULT 'default',
    source_type TEXT NOT NULL,
    source_uri TEXT,
    status TEXT NOT NULL DEFAULT 'started',
    evidence_id TEXT REFERENCES evidence_sources(id) ON DELETE SET NULL,
    error TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS integrity_reports (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL DEFAULT 'default',
    ok INTEGER NOT NULL,
    issue_count INTEGER NOT NULL,
    report_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_registry (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL DEFAULT 'default',
    source_type TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    default_quality DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    review_required INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(project_id, source_type)
);

CREATE TABLE IF NOT EXISTS timeline_events (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL DEFAULT 'default',
    evidence_id TEXT REFERENCES evidence_sources(id) ON DELETE SET NULL,
    claim_id TEXT REFERENCES memory_claims(id) ON DELETE SET NULL,
    span_id TEXT REFERENCES token_spans(id) ON DELETE SET NULL,
    event_date TEXT NOT NULL,
    date_precision TEXT NOT NULL DEFAULT 'day',
    description TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS citation_records (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL DEFAULT 'default',
    citation_set_id TEXT NOT NULL,
    question TEXT NOT NULL,
    citation_label TEXT NOT NULL,
    evidence_id TEXT REFERENCES evidence_sources(id) ON DELETE SET NULL,
    claim_id TEXT REFERENCES memory_claims(id) ON DELETE SET NULL,
    span_id TEXT REFERENCES token_spans(id) ON DELETE SET NULL,
    quote_text TEXT NOT NULL,
    source_title TEXT,
    source_uri TEXT,
    char_start INTEGER,
    char_end INTEGER,
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS memory_capsules (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL DEFAULT 'default',
    capsule_type TEXT NOT NULL,
    title TEXT NOT NULL,
    summary_text TEXT NOT NULL,
    claim_ids_json TEXT NOT NULL DEFAULT '[]',
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS retention_actions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL DEFAULT 'default',
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    actor TEXT,
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

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
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.5,
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

CREATE INDEX IF NOT EXISTS idx_pg_chunks_tsv ON text_chunks USING GIN (chunk_tsv);
CREATE INDEX IF NOT EXISTS idx_pg_claims_tsv ON memory_claims USING GIN (claim_tsv);

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

CREATE TABLE IF NOT EXISTS retrieval_eval_suites (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL DEFAULT 'default',
    name TEXT NOT NULL,
    case_ids_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_evidence_project ON evidence_sources(project_id);
CREATE INDEX IF NOT EXISTS idx_evidence_project_sha ON evidence_sources(project_id, sha256);
CREATE UNIQUE INDEX IF NOT EXISTS idx_evidence_project_sha_unique ON evidence_sources(project_id, sha256);
CREATE INDEX IF NOT EXISTS idx_chunks_evidence ON text_chunks(evidence_id);
CREATE INDEX IF NOT EXISTS idx_claims_project_status ON memory_claims(project_id, status);
CREATE INDEX IF NOT EXISTS idx_claims_subject_predicate ON memory_claims(subject, predicate);
CREATE INDEX IF NOT EXISTS idx_links_claim ON claim_evidence_links(claim_id);
CREATE INDEX IF NOT EXISTS idx_support_spans_claim ON claim_support_spans(claim_id, created_at);
CREATE INDEX IF NOT EXISTS idx_support_spans_evidence ON claim_support_spans(evidence_id);
CREATE INDEX IF NOT EXISTS idx_entities_norm ON entities(normalized_name, entity_type);
CREATE INDEX IF NOT EXISTS idx_mentions_entity ON entity_mentions(entity_id);
CREATE INDEX IF NOT EXISTS idx_lifecycle_claim ON lifecycle_events(claim_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_owner ON embeddings(owner_type, owner_id);
CREATE INDEX IF NOT EXISTS idx_projects_name ON projects(name);
CREATE INDEX IF NOT EXISTS idx_review_claim ON review_actions(claim_id);
CREATE INDEX IF NOT EXISTS idx_relationships_source ON claim_relationships(source_claim_id);
CREATE INDEX IF NOT EXISTS idx_relationships_target ON claim_relationships(target_claim_id);
CREATE INDEX IF NOT EXISTS idx_ingestion_project ON ingestion_jobs(project_id, status);
CREATE INDEX IF NOT EXISTS idx_integrity_project ON integrity_reports(project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_source_registry_project ON source_registry(project_id, source_type);
CREATE INDEX IF NOT EXISTS idx_timeline_project_date ON timeline_events(project_id, event_date);
CREATE INDEX IF NOT EXISTS idx_citation_records_set ON citation_records(citation_set_id);
CREATE INDEX IF NOT EXISTS idx_citation_records_project ON citation_records(project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_capsules_project ON memory_capsules(project_id, capsule_type);
CREATE INDEX IF NOT EXISTS idx_retention_project ON retention_actions(project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_ledger_project_created ON memory_ledger(project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_ledger_object ON memory_ledger(object_type, object_id);
CREATE INDEX IF NOT EXISTS idx_claim_clusters_project ON claim_clusters(project_id, cluster_key);
CREATE INDEX IF NOT EXISTS idx_eval_cases_project ON retrieval_eval_cases(project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_api_request_audit_created ON api_request_audit(created_at);
