# PostgreSQL Proof - FEME v0.7.5

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

- Docker-backed Postgres integration proof command is unchanged and remains the required v0.7.5 proof path.
- Preserve the exact raw test output in `docs/proof/postgres_v0_7_5.txt` after running the live command externally.
- In this workspace, Postgres live proof may skip when `psycopg` and DSN are not configured.

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

Docker-backed Postgres integration proof passed in prior runs and remains required for v0.7.5 release evidence capture.

High-concurrency/load behavior is not yet claimed production-grade and still requires expanded validation.
