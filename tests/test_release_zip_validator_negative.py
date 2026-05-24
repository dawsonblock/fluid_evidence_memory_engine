from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_validate_release_zip_fails_on_forbidden_artifacts(tmp_path):
    root = _repo_root()
    bad_zip = tmp_path / "bad_release.zip"

    # Intentionally include paths matched by scripts/validate-release-zip.sh
    with zipfile.ZipFile(bad_zip, mode="w") as archive:
        archive.writestr("pkg/.pytest_cache/state", "x")
        archive.writestr("pkg/__pycache__/module.cpython-311.pyc", "x")
        archive.writestr("pkg/.DS_Store", "x")

    proc = subprocess.run(
        ["bash", "scripts/validate-release-zip.sh", str(bad_zip)],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode != 0
    combined = (proc.stdout + "\n" + proc.stderr).lower()
    assert "forbidden artifacts found" in combined


def test_validate_release_zip_fails_on_obvious_db_filename(tmp_path):
    root = _repo_root()
    bad_zip = tmp_path / "bad_db_name.zip"

    with zipfile.ZipFile(bad_zip, mode="w") as archive:
        archive.writestr("pkg/$DB_PATH", "not-even-a-real-db")

    proc = subprocess.run(
        ["bash", "scripts/validate-release-zip.sh", str(bad_zip)],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode != 0
    combined = (proc.stdout + "\n" + proc.stderr).lower()
    assert "sqlite database artifact names" in combined


def test_validate_release_zip_fails_on_empty_archive(tmp_path):
    root = _repo_root()
    bad_zip = tmp_path / "empty.zip"
    bad_zip.write_bytes(b"")

    proc = subprocess.run(
        ["bash", "scripts/validate-release-zip.sh", str(bad_zip)],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode != 0
    combined = (proc.stdout + "\n" + proc.stderr).lower()
    assert "invalid release zip" in combined


def test_validate_release_zip_fails_on_corrupt_archive(tmp_path):
    root = _repo_root()
    bad_zip = tmp_path / "corrupt.zip"
    bad_zip.write_bytes(b"not-a-zip")

    proc = subprocess.run(
        ["bash", "scripts/validate-release-zip.sh", str(bad_zip)],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode != 0
    combined = (proc.stdout + "\n" + proc.stderr).lower()
    assert "integrity" in combined
