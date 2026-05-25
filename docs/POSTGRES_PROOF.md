# PostgreSQL Proof - FEME v0.8.3

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

## Proof file

Raw test output: `docs/proof/postgres_v0_8_3.txt`

To capture it externally:

```bash
docker compose --profile postgres up -d postgres
export FEME_DB_BACKEND=postgres
export FEME_POSTGRES_DSN="postgresql://feme:feme_dev_password@localhost:5432/feme"
export FEME_TEST_POSTGRES_DSN="postgresql://feme:feme_dev_password@localhost:5432/feme"
python -m pytest -q \
  tests/test_v07_postgres_live_integration.py \
  tests/test_postgres_load_smoke.py \
  tests/test_postgres_concurrency_smoke.py \
  | tee docs/proof/postgres_v0_8_3.txt
```

FEME v0.8.3 includes a Docker-backed Postgres proof artifact path at `docs/proof/postgres_v0_8_3.txt`.
It proves the bundled integration, load, and concurrency smoke tests for the included suite; it does not prove high-scale production behavior.

Postgres proof artifact is included at `docs/proof/postgres_v0_8_3.txt`. This
proves the included Docker-backed integration, load, and concurrency smoke
tests. It does not prove high-scale production load or high-concurrency deployment
behavior.

In this workspace, Postgres live proof may skip when `psycopg` and DSN are not configured.

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
- `claim_evidence_links` persists split semantics (`evidence_relation` support label + `evidence_kind` derivation type)

## Not yet proven

- high-concurrency ingestion at production load
- large-scale retrieval benchmarking
- pgvector semantic search
- full user/session RBAC (current release provides scoped API-key authorization roles)

## Notes

Docker-backed Postgres integration proof remains part of the v0.8.3 release evidence set.

The v0.8.3 extraction contract accepts `support_relation` and `evidence_kind` with compatibility fallback from legacy `evidence_relation` in structured payloads.

High-concurrency/load behavior is not yet claimed production-grade and still requires expanded validation.
