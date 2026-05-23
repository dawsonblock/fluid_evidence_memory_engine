from __future__ import annotations

import os
from dataclasses import dataclass


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    db_backend: str = os.getenv("FEME_DB_BACKEND", "sqlite").lower()
    db_path: str = os.getenv("FEME_DB_PATH", "./memory.db")
    postgres_dsn: str = os.getenv(
        "FEME_POSTGRES_DSN", os.getenv("DATABASE_URL", "")
    )
    project_id: str = os.getenv("FEME_PROJECT_ID", "default")
    tokenizer: str = os.getenv("FEME_TOKENIZER", "fallback")
    max_chunk_tokens: int = int(os.getenv("FEME_MAX_CHUNK_TOKENS", "900"))
    chunk_overlap_tokens: int = int(
        os.getenv("FEME_CHUNK_OVERLAP_TOKENS", "120")
    )
    api_auth_required: bool = _as_bool(
        os.getenv("FEME_API_AUTH_REQUIRED"), False
    )
    api_key_readonly: str = os.getenv("FEME_API_KEY_READONLY", "")
    api_key_viewer: str = os.getenv(
        "FEME_API_KEY_VIEWER", os.getenv("FEME_API_KEY_READONLY", "")
    )
    api_key_reviewer: str = os.getenv("FEME_API_KEY_REVIEWER", "")
    api_key_editor: str = os.getenv("FEME_API_KEY_EDITOR", "")
    api_key_admin: str = os.getenv(
        "FEME_API_KEY_ADMIN", os.getenv("FEME_API_KEY", "")
    )


def get_settings() -> Settings:
    return Settings()
