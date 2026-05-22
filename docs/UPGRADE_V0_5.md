# FEME v0.5 Upgrade Notes

v0.5 is the runtime-hardening release. v0.4 introduced governance surfaces; v0.5 adds the foundation needed to run those surfaces as auditable operations instead of loose helper functions.

## Added

### Storage abstraction

New package:

```text
src/feme/storage/
  base.py
  sqlite_store.py
  postgres_store.py
  transactions.py
```

`SQLiteStore` is the tested local runtime. `PostgresStore` is an import-safe PostgreSQL adapter shell with capability reporting and explicit dependency handling. It does not silently translate all SQLite SQL paths; it gives the project a clean seam for moving modules onto the Postgres backend without hiding dialect differences.

### Idempotent migrations

New module:

```text
src/feme/migrations.py
```

`MigrationManager.apply_all()` creates and records v0.5 runtime tables. `Database.init()` now applies these migrations after the base schema.

### Memory ledger

New module:

```text
src/feme/ledger.py
```

`memory_ledger` records append-only governance events with a simple hash chain:

```text
ingestion_started
evidence_ingested
claim_written
clusters_rebuilt
ingestion_finished
ingestion_failed
```

Use:

```bash
feme ledger-list --db memory.sqlite
feme ledger-verify --db memory.sqlite
```

### Governed ingestion pipeline

New module:

```text
src/feme/runtime_pipeline.py
```

`TransactionalIngestionPipeline` wraps ingestion, claim extraction, write-governor commits, contradiction scanning, cluster rebuilds, job status updates, and ledger events.

Use:

```bash
feme ingest-governed \
  --db memory.sqlite \
  --text "Use PostgreSQL as canonical memory. Claims must link to spans." \
  --source-type official_record \
  --actor operator
```

### Claim canonicalization

New module:

```text
src/feme/claim_canonicalizer.py
```

Creates deterministic `claim_clusters` grouped by normalized subject/predicate and selects a canonical claim by confidence and source quality.

Use:

```bash
feme claim-clusters-rebuild --db memory.sqlite
feme claim-clusters --db memory.sqlite
```

### Retrieval evaluation suites

New module:

```text
src/feme/retrieval_eval_suite.py
```

Persist evaluation cases and run project-level retrieval checks.

Use:

```bash
feme eval-add-case --db memory.sqlite "canonical memory" --expected-term PostgreSQL
feme eval-suite --db memory.sqlite
```

### Runtime health

New module:

```text
src/feme/runtime.py
```

Reports backend health and store capabilities.

Use:

```bash
feme runtime-health --db memory.sqlite
```

## New database tables

```text
schema_migrations
memory_ledger
claim_clusters
retrieval_eval_cases
retrieval_eval_suites
```

## API additions

```text
POST /runtime/migrate
POST /ingest/governed
GET  /ledger
GET  /ledger/verify
POST /claims/clusters/rebuild
GET  /claims/clusters
POST /eval/cases
POST /eval/suite
```

## Status

SQLite remains the fully tested backend. PostgreSQL is now represented as a real runtime adapter boundary and schema target, but most existing modules still use SQLite-oriented SQL. The next step is to port selected high-volume paths to the `MemoryStore` contract.
