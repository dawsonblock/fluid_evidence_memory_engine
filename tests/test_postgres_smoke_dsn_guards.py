from __future__ import annotations

import os
import tempfile

import pytest

from . import test_postgres_concurrency_smoke as concurrency_smoke
from . import test_postgres_load_smoke as load_smoke


@pytest.mark.parametrize(
    ("module", "env_value"),
    [
        (load_smoke, None),
        (concurrency_smoke, None),
        (
            load_smoke,
            "sqlite:///tmp/feme.db",
        ),
        (
            concurrency_smoke,
            "sqlite:///tmp/feme.db",
        ),
        (
            load_smoke,
            "postgresql://USER:PASSWORD@HOST:5432/DBNAME",
        ),
        (
            concurrency_smoke,
            "postgresql://USER:PASSWORD@HOST:5432/DBNAME",
        ),
    ],
)
def test_live_postgres_dsn_uses_sqlite_fallback_for_invalid_or_example_values(
    monkeypatch: pytest.MonkeyPatch,
    module,
    env_value: str | None,
):
    monkeypatch.delenv("FEME_POSTGRES_DSN", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    if env_value is None:
        monkeypatch.delenv("FEME_DB", raising=False)
    else:
        monkeypatch.setenv("FEME_DB", env_value)

    dsn = module._live_postgres_dsn()
    assert dsn.startswith(os.path.join(tempfile.gettempdir(), "feme_"))
    assert dsn.endswith(".db")


@pytest.mark.parametrize("module", [load_smoke, concurrency_smoke])
def test_live_postgres_dsn_accepts_real_postgres_values(
    monkeypatch: pytest.MonkeyPatch,
    module,
):
    monkeypatch.delenv("FEME_POSTGRES_DSN", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    dsn = "postgresql://feme@localhost:5432/feme"
    monkeypatch.setenv("FEME_DB", dsn)

    assert module._live_postgres_dsn() == dsn


@pytest.mark.parametrize("module", [load_smoke, concurrency_smoke])
@pytest.mark.parametrize("env_name", ["FEME_POSTGRES_DSN", "DATABASE_URL"])
def test_live_postgres_dsn_accepts_fallback_env_vars(
    monkeypatch: pytest.MonkeyPatch,
    module,
    env_name: str,
):
    dsn = "postgresql://feme@localhost:5432/feme"
    monkeypatch.delenv("FEME_DB", raising=False)
    monkeypatch.delenv("FEME_POSTGRES_DSN", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv(env_name, dsn)

    assert module._live_postgres_dsn() == dsn


@pytest.mark.parametrize("module", [load_smoke, concurrency_smoke])
def test_live_postgres_dsn_prefers_real_fallback_over_placeholder_primary(
    monkeypatch: pytest.MonkeyPatch,
    module,
):
    monkeypatch.setenv("FEME_DB", "postgresql://USER:PASSWORD@HOST:5432/DBNAME")
    monkeypatch.setenv("FEME_POSTGRES_DSN", "postgresql://feme@localhost:5432/feme")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert module._live_postgres_dsn() == "postgresql://feme@localhost:5432/feme"
