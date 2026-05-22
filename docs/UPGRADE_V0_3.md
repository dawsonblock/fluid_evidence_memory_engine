# Upgrade v0.3 — Governance, Integrity, and Provenance Layer

v0.3 turns the v0.2 memory engine from a working evidence/claim prototype into a more controlled memory runtime. The focus is not adding more memory. The focus is preventing bad memory from becoming authority.

## Added

### Project registry

A `projects` table now tracks isolated memory workspaces. Evidence, claims, retrieval, integrity checks, and statistics can be scoped by `project_id`.

### Ingestion jobs

Every non-duplicate ingestion now records an `ingestion_jobs` row with status, source type, source URI, linked evidence ID, timestamps, and metadata.

### Duplicate evidence suppression

`EvidenceIngestor.ingest_text(..., deduplicate=True)` detects identical source text inside the same project by SHA-256. It returns the existing evidence ID instead of duplicating chunks, spans, embeddings, and claims.

### Sensitivity detection

The new `sensitive.py` module detects basic PII-like patterns:

- Email addresses
- Phone numbers
- Possible payment cards
- Possible Canadian SIN-like patterns
- Possible street addresses

This is deterministic pattern matching, not a legal privacy classifier. It is intended as a write-governor signal and metadata flag.

### Review queue

The new `ReviewQueue` can list pending claims and apply review actions:

- `accept`
- `verify`
- `reject`
- `archive`
- `dispute`
- `supersede`
- `restore`

Review actions are recorded in `review_actions` and mirrored into `lifecycle_events`.

### Provenance graph

`ProvenanceGraph.trace_claim(claim_id)` returns:

- Claim record
- Supporting evidence links
- Source metadata
- Token-span text
- Contradictions
- Review history
- Lifecycle history

This is the main proof chain API for answer verification and legal-style audit behavior.

### Integrity checker

`IntegrityChecker.run(project_id=...)` checks:

- Snapshot hash mismatches
- Token-span hash mismatches
- Span/chunk text mismatch
- Unsupported active claims
- Missing claim embeddings
- Duplicate evidence hashes
- Unresolved contradictions

Reports are persisted to `integrity_reports`.

### Backup manager

`BackupManager.backup(path)` uses SQLite's backup API to create a consistent database copy.

### Import support

Project exports can now be imported into another initialized database with `ProjectExporter.import_project(...)`.

### Retrieval diversification

Search now applies maximal marginal relevance style reranking. This reduces repeated near-duplicate context and improves evidence coverage inside limited token budgets.

### Context risk summary

Context packets now include a `risk_summary` showing unsupported, disputed, and pending-review claims.

## New CLI commands

```bash
feme project-stats --project-id default
feme review-list --project-id default
feme review-action CLAIM_ID verify --reviewer Dawson --reason "checked source"
feme trace-claim CLAIM_ID
feme integrity-check --project-id default
feme backup-db --out feme_backup.sqlite
feme import-project export.json
```

## New API endpoints

```text
GET  /projects
GET  /projects/{project_id}/stats
GET  /review/pending
POST /review/action
GET  /claims/{claim_id}/trace
POST /integrity/check
POST /backup
```

## New tests

v0.3 adds tests for:

- Sensitive data detection/redaction
- Duplicate ingestion suppression
- Project-scoped claim creation
- Review actions
- Provenance tracing
- Integrity reports
- Project export/import
- SQLite backup creation

## Current limits

- Claim extraction is still heuristic. It is useful for bootstrapping, but a stronger extractor should be added later.
- Sensitive detection is pattern-based. It does not replace a full privacy classifier.
- PostgreSQL schema remains a draft. SQLite is the tested backend in this ZIP.
- Embeddings are still local hashing embeddings. This keeps the build portable, but serious deployment should add a real embedding provider or local model.
