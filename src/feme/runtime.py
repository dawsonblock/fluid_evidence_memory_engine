from __future__ import annotations

from typing import Any

from . import __version__
from .config import get_settings
from .db import Database
from .embeddings import embedding_runtime_capabilities
from .migration_health import check_migration_completeness
from .postgres_db import PostgresDatabase
from .storage import PostgresStore, SQLiteStore


def make_database(db: str | None = None, *, backend: str | None = None) -> Any:
    settings = get_settings()
    selected_backend = (backend or settings.db_backend or "sqlite").lower()
    target = db or settings.postgres_dsn or settings.db_path
    if selected_backend == "postgres" or str(target).startswith(
        ("postgres://", "postgresql://")
    ):
        dsn = db or settings.postgres_dsn or settings.db_path
        if not dsn or not str(dsn).startswith(("postgres://", "postgresql://")):
            raise ValueError(
                "PostgreSQL backend selected but no DSN was provided. Set FEME_POSTGRES_DSN or pass --db postgresql://..."
            )
        return PostgresDatabase(str(dsn))
    return Database(str(db or settings.db_path))


def runtime_health(database: Any | None = None) -> dict:
    db = database or make_database()
    if getattr(db, "backend", "sqlite") == "postgres":
        store = PostgresStore(db.dsn)
    else:
        store = SQLiteStore(db)
    health = store.health()
    caps = store.capabilities()
    embeddings = embedding_runtime_capabilities(db)
    migration = check_migration_completeness(db)
    return {
        "package_version": __version__,
        "schema_version": migration["schema_version"],
        "migration_status": migration["migration_status"],
        "missing_schema_features": migration["missing_schema_features"],
        "last_migration_error": migration["last_migration_error"],
        "last_migration_error_at": migration["last_migration_error_at"],
        "health": health.__dict__,
        "capabilities": caps.__dict__,
        "embeddings": embeddings,
    }
