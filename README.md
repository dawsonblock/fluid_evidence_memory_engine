# Fluid Evidence Memory Engine v0.6 PostgreSQL Runtime

A practical implementation of a **token-anchored, claim-based long-context memory system** with SQLite and PostgreSQL runtime paths.

Core rule:

> Raw sources are authoritative. Claims are structured interpretations. Summaries are disposable. Embeddings are retrieval helpers only.

This repository is a working starter stack for accurate long-context memory with immutable evidence records, token spans, structured claims, contradiction tracking, lifecycle control, review governance, source policy controls, citation packets, context-packet construction, ledger governance, and a runnable PostgreSQL backend facade.

It is not a finished legal, medical, or financial authority system.

## What v0.6 adds

- Runnable PostgreSQL backend selection through `FEME_DB_BACKEND=postgres`
- `PostgresDatabase` facade compatible with existing FEME modules
- SQL compatibility translator for:
  - SQLite `?` placeholders → psycopg `%s`
  - `INSERT OR IGNORE` → `ON CONFLICT DO NOTHING`
  - `INSERT OR REPLACE` on `schema_meta` → Postgres upsert
  - scalar `MIN(1.0, ...)` → `LEAST(1.0, ...)`
- PostgreSQL runtime schema aligned with existing SQLite tables
- PostgreSQL-compatible FTS side tables for current ingestion/maintenance paths
- Runtime factory: `make_database()` selects SQLite or Postgres from config/env/DSN
- API startup can run against SQLite or Postgres
- Docker Compose Postgres profile
- Postgres SQL smoke CLI command
- Expanded tests: `23 passed`

## Architecture

```text
Evidence Vault
  -> TokenTrace spans
  -> Entity + Timeline extraction
  -> Claim extraction
  -> Memory Write Governor
  -> Claim graph + contradictions
  -> Review / source governance
  -> Hybrid retrieval
  -> Context packet
  -> Citation packet / answer scaffold
  -> Verification / audit / retention
  -> Ledger / migrations / backend runtime
```

## Repository layout

```text
fluid_evidence_memory_engine_v0_6_postgres/
  pyproject.toml
  README.md
  CHANGELOG.md
  .env.example
  Dockerfile
  docker-compose.yml
  sql/
    sqlite_schema.sql
    postgres_schema.sql
  src/feme/
    api.py
    answer_builder.py
    audit.py
    backup.py
    chunking.py
    citations.py
    claim_canonicalizer.py
    claim_extractor.py
    cli.py
    config.py
    consolidation.py
    context_builder.py
    contradiction.py
    db.py
    embeddings.py
    entity_extractor.py
    evidence.py
    export_import.py
    integrity.py
    ledger.py
    lifecycle.py
    maintenance.py
    migrations.py
    models.py
    postgres_db.py
    retrieval.py
    runtime.py
    runtime_pipeline.py
    storage/
    verifier.py
    write_governor.py
  docs/
  tests/
```

## Quick start: SQLite

```bash
cd fluid_evidence_memory_engine_v0_6_postgres
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e '.[dev,api]'
pytest -q
```

Initialize SQLite:

```bash
feme init --db ./memory.db
```

Governed ingest:

```bash
feme ingest-governed \
  --db ./memory.db \
  --text "Use PostgreSQL as canonical memory. Claims must link to exact spans." \
  --source-type official_record \
  --actor operator
```

Search:

```bash
feme search --db ./memory.db "canonical memory database" --project-id default
```

Verify ledger:

```bash
feme ledger-verify --db ./memory.db
```

## Quick start: PostgreSQL

Install the Postgres extra:

```bash
pip install -e '.[dev,api,postgres]'
```

Start Postgres with Docker Compose:

```bash
docker compose --profile postgres up -d postgres
```

Initialize the schema:

```bash
FEME_DB_BACKEND=postgres \
FEME_POSTGRES_DSN=postgresql://feme:feme_dev_password@localhost:5432/feme \
feme init
```

Run the same governed ingest path against Postgres:

```bash
FEME_DB_BACKEND=postgres \
FEME_POSTGRES_DSN=postgresql://feme:feme_dev_password@localhost:5432/feme \
feme ingest-governed \
  --text "Use PostgreSQL as canonical memory. Claims must link to exact spans." \
  --source-type official_record \
  --actor operator
```

Search Postgres:

```bash
FEME_DB_BACKEND=postgres \
FEME_POSTGRES_DSN=postgresql://feme:feme_dev_password@localhost:5432/feme \
feme search "canonical memory database"
```

Run the API with Postgres:

```bash
FEME_DB_BACKEND=postgres \
FEME_POSTGRES_DSN=postgresql://feme:feme_dev_password@localhost:5432/feme \
uvicorn feme.api:app --host 0.0.0.0 --port 8000
```

Or use the compose profile:

```bash
docker compose --profile postgres up --build feme-api-postgres
```

## PostgreSQL status

v0.6 changes the status from “schema target only” to **runnable Postgres backend path**.

What is now implemented:

- Postgres runtime object
- Postgres schema initialization
- Postgres health check
- Existing module compatibility through SQL translation
- API/CLI backend selection
- Ingestion/retrieval paths designed to run against Postgres

What remains before calling it production-grade:

- Live Postgres CI with a real database service
- Native Postgres FTS/ranking instead of compatibility fallback
- Full migration history beyond bootstrap schema
- Load/concurrency testing
- Row-level auth/multi-user permission enforcement
- Backup/restore tooling specific to Postgres

## Live Postgres tests

Run only the live Postgres integration suite (skips if DSN is unset):

```bash
FEME_TEST_POSTGRES_DSN=postgresql://feme:feme_dev_password@localhost:5432/feme \
pytest -q tests/test_v07_postgres_live_integration.py
```

Run through docker-compose test profile:

```bash
docker compose --profile test-postgres up --build --abort-on-container-exit feme-tests-postgres
```

## Useful commands

```bash
feme runtime-health
feme postgres-sql-smoke
feme source-list --project-id default
feme answer-scaffold "What database should the memory engine use?"
feme citations "What database should the memory engine use?" --persist
feme integrity-check --project-id default
feme eval-add-case "canonical memory" --expected-term PostgreSQL
feme eval-suite
```

## Important limitations

- Claim extraction is still heuristic and should be replaced by a structured extractor when available.
- Embeddings are deterministic hashing vectors for offline development, not high-quality semantic embeddings.
- PostgreSQL is now runnable, but it has not been live-validated in this container because no Postgres server is available.
- Redaction is a local data-minimization operation, not a legal deletion guarantee.
- The answer scaffold is not a final answer generator; it prepares grounded claims, warnings, and citation labels.
