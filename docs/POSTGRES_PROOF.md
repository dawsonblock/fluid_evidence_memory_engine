# PostgreSQL Proof - FEME v0.7.2

## Environment

- Python: 3.11 (CI), 3.10+ supported
- PostgreSQL: 16
- psycopg: 3.1+
- OS: macOS/Linux (Docker-backed proof)

## Commands

```bash
docker compose --profile postgres up -d postgres
export FEME_DB_BACKEND=postgres
export FEME_POSTGRES_DSN="postgresql://feme:feme_dev_password@localhost:5432/feme"
export FEME_TEST_POSTGRES_DSN="postgresql://feme:feme_dev_password@localhost:5432/feme"
pytest -q tests/test_v07_postgres_live_integration.py
```

Equivalent one-command helper:

```bash
bash scripts/postgres-proof.sh
```

## Result

- `python3.10 -m pytest -q tests/test_v07_postgres_live_integration.py` with Docker Postgres + DSN set -> `10 passed`
- `python3.10 -m pytest -q` local default environment -> `51 passed, 10 skipped`
- default-env suite remains skip-safe when DSN/psycopg are unavailable

## Proven

- migrations execute on live Postgres
- PL/pgSQL ledger trigger is installed
- governed ingest works
- retrieval works
- ledger verification works
- append-only ledger enforcement blocks UPDATE/DELETE
- duplicate evidence suppression works under parallel writers
- source registry review-required behavior is surfaced during ingest
- runtime health reports postgres backend

## Not yet proven

- high-concurrency ingestion at production load
- large-scale retrieval benchmarking
- pgvector semantic search
- full user/session RBAC (current release provides scoped API-key authorization roles)

## Notes

This document is a required release artifact for v0.7 dual-backend alpha packaging.
