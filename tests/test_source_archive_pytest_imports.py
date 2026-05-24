from __future__ import annotations

from pathlib import Path

from tests import test_postgres_smoke_dsn_guards as dsn_guards


def test_local_tests_package_resolves_repo_modules():
    tests_dir = Path(__file__).resolve().parent

    assert Path(dsn_guards.__file__).resolve() == (
        tests_dir / "test_postgres_smoke_dsn_guards.py"
    )
    assert Path(dsn_guards.load_smoke.__file__).resolve() == (
        tests_dir / "test_postgres_load_smoke.py"
    )
    assert Path(dsn_guards.concurrency_smoke.__file__).resolve() == (
        tests_dir / "test_postgres_concurrency_smoke.py"
    )
