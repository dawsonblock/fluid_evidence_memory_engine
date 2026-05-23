# PostgreSQL Proof (v0.7)

This document records reproducible commands and outcomes for PostgreSQL runtime verification.

## Scope

The v0.7 hardening objective is to prove that PostgreSQL runtime behavior is not only present in code, but executable and regression-tested.

## Preconditions

- Python environment includes postgres extra:

```bash
pip install -e '.[dev,api,postgres]'
```

- PostgreSQL service is available (local Docker profile):

```bash
docker compose --profile postgres up -d postgres
```

- DSN variables are set:

```bash
export FEME_DB_BACKEND=postgres
export FEME_POSTGRES_DSN=postgresql://feme:feme_dev_password@localhost:5432/feme
export FEME_TEST_POSTGRES_DSN=postgresql://feme:feme_dev_password@localhost:5432/feme
```

## Required verification commands

1. Targeted regression checks:

```bash
pytest -q tests/test_v06_postgres.py tests/test_v04_upgrade.py
```

2. Live PostgreSQL integration suite:

```bash
pytest -q tests/test_v07_postgres_live_integration.py
```

3. Full test suite:

```bash
pytest -q
```

4. CLI smoke against PostgreSQL:

```bash
feme init
feme runtime-health
feme ingest-governed --text "Use PostgreSQL as canonical memory." --source-type official_record --actor operator
feme search "canonical memory"
feme ledger-verify
```

## Expected outcomes

- No migration errors when applying V07/V08/V09 SQL.
- Ledger append-only trigger is installed and rejects update/delete mutations.
- Governed ingest succeeds in PostgreSQL mode.
- Retrieval returns grounded claim/chunk results.
- Full suite passes with no unexpected skips.

## Latest local evidence snapshot

- Focused SQL/runtime regressions: `python3.10 -m pytest -q tests/test_v06_postgres.py tests/test_v05_runtime.py` -> `14 passed`
- Live PostgreSQL integration: `FEME_TEST_POSTGRES_DSN=postgresql://feme:feme_dev_password@localhost:5432/feme python3.10 -m pytest -q tests/test_v07_postgres_live_integration.py` -> `5 passed, 1 skipped`
- Full suite (default env): `python3.10 -m pytest -q` -> `31 passed, 6 skipped`
- Note: default full-suite skips are expected when live PostgreSQL checks are not enabled by environment.

## Release gate recommendation

Treat this document as a required release artifact update for every v0.7+ package build.
