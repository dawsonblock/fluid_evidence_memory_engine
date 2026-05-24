from __future__ import annotations

import re
import subprocess
import zipfile
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _project_version(root: Path) -> str:
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(
        r'^version\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"',
        text,
        re.MULTILINE,
    )
    assert match, "project version not found in pyproject.toml"
    return match.group(1)


def test_release_zip_excludes_forbidden_artifacts():
    root = _repo_root()
    version = _project_version(root)
    zip_path = (
        root
        / "dist"
        / f"fluid_evidence_memory_engine_v{version.replace('.', '_')}.zip"
    )

    subprocess.run(
        ["bash", "scripts/build-release-zip.sh"],
        cwd=root,
        check=True,
    )
    assert zip_path.exists(), f"expected release archive missing: {zip_path}"

    forbidden_pattern = re.compile(
        r"egg-info/|__pycache__/|\.pyc$|\.pyo$|\.pytest_cache/"
        r"|\.ruff_cache/|\.mypy_cache/|__MACOSX/|/\._|\.DS_Store"
        r"|(^|/)\$DB_PATH$|\.sqlite$|\.sqlite3$|\.db$"
        r"|\.sqlite-journal$|\.db-journal$|\.sqlite-wal$"
        r"|\.sqlite-shm$|\.db-wal$|\.db-shm$|\.env$"
    )

    with zipfile.ZipFile(zip_path) as archive:
        bad_entries = [
            name
            for name in archive.namelist()
            if forbidden_pattern.search(name)
        ]

    assert not bad_entries, (
        f"forbidden artifacts found in {zip_path}: {bad_entries}"
    )
