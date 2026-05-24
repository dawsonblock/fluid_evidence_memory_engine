from __future__ import annotations

import pytest

from tests import test_postgres_concurrency_smoke as concurrency_smoke
from tests import test_postgres_load_smoke as load_smoke


@pytest.mark.parametrize(
    ("module", "env_value", "expected_message"),
    [
        (load_smoke, None, "set FEME_DB to run postgres smoke tests"),
        (
            concurrency_smoke,
            None,
            "set FEME_DB to run postgres smoke tests",
        ),
        (
            load_smoke,
            "sqlite:///tmp/feme.db",
            "FEME_DB must be a PostgreSQL DSN for postgres smoke tests",
        ),
        (
            concurrency_smoke,
            "sqlite:///tmp/feme.db",
            "FEME_DB must be a PostgreSQL DSN for postgres smoke tests",
        ),
        (
            load_smoke,
            "postgresql://USER:PASSWORD@HOST:5432/DBNAME",
            "FEME_DB appears to be an example DSN; set a real Postgres DSN",
        ),
        (
            concurrency_smoke,
            "postgresql://USER:PASSWORD@HOST:5432/DBNAME",
            "FEME_DB appears to be an example DSN; set a real Postgres DSN",
        ),
    ],
)
def test_live_postgres_dsn_skips_invalid_or_example_values(
    monkeypatch: pytest.MonkeyPatch,
    module,
    env_value: str | None,
    expected_message: str,
):
    if env_value is None:
        monkeypatch.delenv("FEME_DB", raising=False)
    else:
        monkeypatch.setenv("FEME_DB", env_value)

    with pytest.raises(pytest.skip.Exception, match=expected_message):
        module._live_postgres_dsn()


@pytest.mark.parametrize("module", [load_smoke, concurrency_smoke])
def test_live_postgres_dsn_accepts_real_postgres_values(
    monkeypatch: pytest.MonkeyPatch,
    module,
):
    dsn = "postgresql://feme@localhost:5432/feme"
    monkeypatch.setenv("FEME_DB", dsn)

    assert module._live_postgres_dsn() == dsn