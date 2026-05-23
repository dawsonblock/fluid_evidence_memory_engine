# v0.6 Upgrade: PostgreSQL Runtime Backend

v0.6 adds a runnable PostgreSQL backend path to FEME.

## Main changes

- Added `src/feme/postgres_db.py`.
- Added runtime backend selection through `FEME_DB_BACKEND` and `FEME_POSTGRES_DSN`.
- Added `make_database()` in `src/feme/runtime.py`.
- Updated CLI/API startup to use the backend factory.
- Rebuilt `sql/postgres_schema.sql` to mirror the SQLite runtime tables.
- Added a Postgres SQL compatibility translator for current SQLite-style module SQL.
- Updated Docker Compose with a Postgres API profile.
- Added Postgres-focused tests that validate SQL rewriting and runtime selection.

## Environment

```bash
FEME_DB_BACKEND=postgres
FEME_POSTGRES_DSN=postgresql://feme:feme_dev_password@localhost:5432/feme
```

## Install

```bash
pip install -e '.[api,postgres]'
```

## Initialize

```bash
FEME_DB_BACKEND=postgres \
FEME_POSTGRES_DSN=postgresql://feme:feme_dev_password@localhost:5432/feme \
feme init
```

## Validate SQL rewriting

```bash
feme postgres-sql-smoke
```

## Remaining hardening

The Postgres backend is now a real runtime path, but it still needs live database CI, native Postgres FTS/ranking, and concurrency/load testing before it should be described as production-grade.

## v0.7 follow-up status

v0.7 adds proof and runtime hygiene on top of this upgrade:

- live Docker-backed Postgres integration tests in CI
- robust PL/pgSQL dollar-quoted migration splitting
- append-only ledger mutation blocking validated on Postgres
- backend-neutral source registry insertion counting

FEME should now be described as a verified dual-backend alpha (SQLite + PostgreSQL live-tested), not production-ready.
