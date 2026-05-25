# Backup and Restore (v0.7)

## SQLite backend

SQLite backup is supported directly through the runtime:

```bash
feme backup --out ./backups/feme.sqlite
```

The backup command uses SQLite's native backup/VACUUM behavior for consistent local snapshots.

## PostgreSQL backend

In v0.7, runtime backup helpers do not implement PostgreSQL dumps.

When `FEME_DB_BACKEND=postgres`, backup commands return an explicit error instead of attempting a SQLite-only path.

Use one of the following safe alternatives:

1. Database-native backup:

```bash
pg_dump "postgresql://feme:feme_dev_password@localhost:5432/feme" -Fc -f ./backups/feme.dump
```

1. FEME project export for logical data transfer:

```bash
feme export-project default --out ./backups/default_project.json
```

## Restore guidance

SQLite restore:

```bash
cp ./backups/feme.sqlite ./memory.db
```

PostgreSQL restore from pg_dump archive:

```bash
pg_restore --clean --if-exists --dbname "postgresql://feme:feme_dev_password@localhost:5432/feme" ./backups/feme.dump
```

Project-level restore (both backends):

```bash
feme import-project --in ./backups/default_project.json
```

## Scope note

This is intentionally conservative for v0.7 dual-backend alpha. Full PostgreSQL backup orchestration can be added in a later release.
