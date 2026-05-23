# Fluid Evidence Memory Engine

![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![Backend](https://img.shields.io/badge/backends-SQLite%20%7C%20PostgreSQL-0A7EA4)
![Interface](https://img.shields.io/badge/interface-CLI%20%7C%20API-2F855A)
![Tests](https://img.shields.io/badge/tests-pytest-6E44FF?logo=pytest&logoColor=white)

Token-anchored, claim-based long-context memory with strict evidence provenance, review governance, and dual runtime support (SQLite + PostgreSQL).

> Raw sources are authoritative. Claims are structured interpretations. Summaries are disposable. Embeddings are retrieval helpers only.

## Jump To

- [Why FEME](#why-feme)
- [Quick Start](#quick-start)
- [Testing](#testing)
- [Practical Examples](#practical-examples)
- [API Example](#api-example)
- [Contributing](#contributing)
- [FAQ](#faq)
- [Current Status](#current-status)
- [Documentation](#documentation)

---

## Why FEME

FEME is a practical memory runtime for systems that need grounded answers and auditable reasoning. It keeps evidence immutable, ties claims to spans, tracks contradictions, and exposes retrieval and governance workflows through both CLI and API.

### Core capabilities

| Area | What you get |
|---|---|
| Evidence integrity | Immutable source records, snapshots, and token spans |
| Claim quality | Canonicalization, contradiction tracking, and write governance |
| Retrieval | Hybrid retrieval with lexical + embedding-assisted ranking |
| Governance | Source policy, review workflow, lifecycle and retention controls |
| Auditability | Ledger chain verification, provenance packets, citation scaffolding |
| Runtime | SQLite and PostgreSQL runtime selection with shared APIs |

---

## Architecture

```mermaid
flowchart TD
    A[Raw Evidence] --> B[Chunking + Token Spans]
    B --> C[Claim Extraction]
    C --> D[Write Governor]
    D --> E[Claim Graph]
    E --> F[Contradiction + Consolidation]
    F --> G[Hybrid Retrieval]
    G --> H[Context + Citations]
    H --> I[Answer Scaffold]

    A --> J[Evidence Vault]
    D --> K[Ledger + Audit]
    K --> L[Integrity + Verification]
```

---

## Quick Start

### 1) Install

Recommended one-command setup:

```bash
bash scripts/dev-setup.sh
source .venv/bin/activate
```

Manual setup:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,api]'
```

For PostgreSQL support:

```bash
pip install -e '.[dev,api,postgres]'
```

### 2) SQLite flow (local default)

```bash
feme init --db ./memory.db

feme ingest-governed \
  --db ./memory.db \
  --text "Use PostgreSQL as canonical memory. Claims must link to exact spans." \
  --source-type official_record \
  --actor operator

feme search --db ./memory.db "canonical memory database" --project-id default
feme ledger-verify --db ./memory.db
```

### 3) PostgreSQL flow

Start local Postgres:

```bash
docker compose --profile postgres up -d postgres
```

Initialize and run:

```bash
export FEME_DB_BACKEND=postgres
export FEME_POSTGRES_DSN=postgresql://feme:feme_dev_password@localhost:5432/feme

feme init
feme ingest-governed \
  --text "Use PostgreSQL as canonical memory. Claims must link to exact spans." \
  --source-type official_record \
  --actor operator
feme search "canonical memory database"
```

Run API against Postgres:

```bash
uvicorn feme.api:app --host 0.0.0.0 --port 8000
```

Or run the compose API profile:

```bash
docker compose --profile postgres up --build feme-api-postgres
```

---

## Testing

Run the full test suite:

```bash
pytest -q
```

Run live PostgreSQL integration tests (skips when DSN is unset):

```bash
export FEME_TEST_POSTGRES_DSN=postgresql://feme:feme_dev_password@localhost:5432/feme
pytest -q tests/test_v07_postgres_live_integration.py
```

One-command Docker + live-proof run:

```bash
bash scripts/postgres-proof.sh
```

Run live PostgreSQL tests through Docker Compose:

```bash
docker compose --profile test-postgres up --build --abort-on-container-exit feme-tests-postgres
```

---

## Useful CLI Commands

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

---

## Practical Examples

### Example 1: Evidence in, grounded search out

```bash
feme init --db ./memory.db
feme ingest-governed \
  --db ./memory.db \
  --text "Incident report: service latency increased after configuration drift." \
  --source-type official_record \
  --actor ops_user
feme search --db ./memory.db "configuration drift latency" --project-id default
```

### Example 2: Build citation-ready answer scaffolding

```bash
feme answer-scaffold "Why did latency increase?" --db ./memory.db
feme citations "Why did latency increase?" --db ./memory.db --persist
```

### Example 3: Health + integrity check before release

```bash
feme runtime-health --db ./memory.db
feme integrity-check --db ./memory.db --project-id default
feme ledger-verify --db ./memory.db
```

---

## API Example

Run the API:

```bash
uvicorn feme.api:app --host 0.0.0.0 --port 8000
```

Ingest evidence via HTTP:

```bash
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "text": "The operations report confirms configuration drift before latency spike.",
    "source_type": "official_record",
    "project_id": "default"
  }'
```

Search via HTTP:

```bash
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "configuration drift",
    "project_id": "default",
    "top_k": 10
  }'
```

---

## Contributing

1. Create and activate a virtual environment.
2. Install editable dependencies.
3. Run tests before opening a pull request.
4. Keep changes small and scoped; include or update tests for behavior changes.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,api,postgres]'
pytest -q
```

Optional quality checks:

```bash
ruff check src tests
```

---

## FAQ

### Is PostgreSQL fully supported?

PostgreSQL is supported for runtime use, migrations, API/CLI flows, and live integration tests. Some production-hardening areas are still evolving (authz depth, broader adapter parity, backup/restore runbooks).

### Why are some tests skipped?

Live PostgreSQL integration tests skip automatically when FEME_TEST_POSTGRES_DSN is not set.

### Does FEME generate final answers?

FEME focuses on evidence-grounded memory, context packets, and citation scaffolds. It is not positioned as a standalone final-answer authority system.

### Are embeddings model-quality?

By default, embeddings are deterministic hashing vectors intended for reproducible development workflows, not top-tier semantic quality.

---

## Project Layout

```text
src/feme/
  api.py                FastAPI surface
  cli.py                Typer CLI
  runtime.py            Backend selection and runtime wiring
  db.py                 SQLite backend
  postgres_db.py        PostgreSQL facade + SQL compatibility rewrite
  evidence.py           Evidence ingestion pipeline
  runtime_pipeline.py   Transactional governed ingest
  retrieval.py          Hybrid retrieval planner
  ledger.py             Hash-chain append and verification
  migrations.py         Runtime migration manager
tests/
  test_ingest.py
  test_retrieval.py
  test_v06_postgres.py
  test_v07_postgres_live_integration.py
```

---

## Current Status

Implemented:

- Runnable SQLite and PostgreSQL backend paths
- Native PostgreSQL lexical indexing artifacts and migration coverage
- Shared transaction wiring for governed ingest path
- Ledger append serialization and append-only protections
- Duplicate evidence collision hardening with concurrency test coverage
- Live PostgreSQL integration test suite and CI wiring (dual-backend alpha proof)

Still evolving:

- Broader adapter abstraction adoption across remaining modules
- Deeper authz and multi-tenant isolation controls
- Stronger production backup/restore automation (v0.7 documents explicit pg_dump/export workflow)
- Higher-fidelity extraction and embedding backends

---

## Safety and Scope Notes

- Not a legal, medical, or financial authority system.
- Extraction is heuristic and may require model-backed replacement for high-stakes use.
- Embeddings are deterministic hashing vectors by default, optimized for reproducible offline development.
- Redaction support is data-minimization tooling, not a legal deletion guarantee.

---

## Documentation

- docs/ARCHITECTURE.md
- docs/BACKUP_RESTORE.md
- docs/NEXT_STEPS.md
- docs/POSTGRES_PROOF.md
- docs/UPGRADE_V0_6_POSTGRES.md
- CHANGELOG.md
