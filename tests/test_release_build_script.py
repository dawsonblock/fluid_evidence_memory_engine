from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _has_git() -> bool:
    return shutil.which("git") is not None


def _is_git_repo(root: Path) -> bool:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def _git_status_for_egg_info(root: Path) -> str:
    proc = subprocess.run(
        [
            "git",
            "status",
            "--short",
            "--",
            "src/fluid_evidence_memory_engine.egg-info",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout


def _project_version(root: Path) -> str:
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    marker = 'version = "'
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(marker):
            return stripped.removeprefix(marker).split('"', 1)[0]
    raise AssertionError("project version not found in pyproject.toml")


def _copy_source_tree(src: Path, dst: Path) -> None:
    shutil.copytree(
        src,
        dst,
        ignore=shutil.ignore_patterns(
            ".git",
            "dist",
            ".venv",
            "__pycache__",
            "*.pyc",
            "*.pyo",
            ".pytest_cache",
            ".ruff_cache",
            ".mypy_cache",
            "__MACOSX",
            ".DS_Store",
            "._*",
        ),
    )


@pytest.mark.skipif(
    not _has_git(),
    reason="git is required for release script regression check",
)
def test_build_release_zip_does_not_modify_tracked_egg_info():
    root = _repo_root()
    if not _is_git_repo(root):
        pytest.skip("requires a git worktree")

    before = _git_status_for_egg_info(root)

    subprocess.run(
        ["bash", "scripts/build-release-zip.sh"],
        cwd=root,
        check=True,
    )

    after = _git_status_for_egg_info(root)
    assert after == before


def test_build_release_zip_falls_back_without_git_repo(tmp_path: Path):
    root = _repo_root()
    extracted = tmp_path / "source"
    _copy_source_tree(root, extracted)

    version = _project_version(extracted)
    version_us = version.replace(".", "_")
    zip_path = extracted / "dist" / f"fluid_evidence_memory_engine_v{version_us}.zip"

    subprocess.run(
        ["bash", "scripts/build-release-zip.sh"],
        cwd=extracted,
        check=True,
    )

    assert zip_path.exists(), f"expected release archive missing: {zip_path}"
    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()

    assert ".git/" not in names
    assert "pyproject.toml" in names
    assert "tests/test_postgres_smoke_dsn_guards.py" in names


def test_build_release_zip_excludes_runtime_databases_in_fallback_path(
    tmp_path: Path,
):
    root = _repo_root()
    extracted = tmp_path / "source"
    _copy_source_tree(root, extracted)

    version = _project_version(extracted)
    version_us = version.replace(".", "_")
    zip_path = extracted / "dist" / f"fluid_evidence_memory_engine_v{version_us}.zip"

    (extracted / "$DB_PATH").write_bytes(b"SQLite format 3\x00runtime")
    (extracted / "test.sqlite").write_bytes(b"SQLite format 3\x00test")
    (extracted / "test.sqlite-wal").write_bytes(b"wal")
    (extracted / "test.sqlite-shm").write_bytes(b"shm")
    (extracted / "test.db").write_bytes(b"SQLite format 3\x00db")
    nested = extracted / "nested"
    nested.mkdir()
    (nested / "$DB_PATH").write_bytes(b"SQLite format 3\x00nested")

    subprocess.run(
        ["bash", "scripts/build-release-zip.sh"],
        cwd=extracted,
        check=True,
    )

    assert zip_path.exists(), f"expected release archive missing: {zip_path}"
    assert zip_path.stat().st_size > 0, "expected non-empty release archive"

    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()

    assert "$DB_PATH" not in names
    assert "nested/$DB_PATH" not in names
    assert "test.sqlite" not in names
    assert "test.sqlite-wal" not in names
    assert "test.sqlite-shm" not in names
    assert "test.db" not in names
