from __future__ import annotations

import sqlite3
import subprocess
import zipfile
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_validator_rejects_extensionless_sqlite(tmp_path: Path):
    root = _repo_root()
    db_path = tmp_path / "$DB_PATH"
    con = sqlite3.connect(db_path)
    con.execute("create table t(id integer)")
    con.commit()
    con.close()

    zip_path = tmp_path / "bad_release.zip"
    with zipfile.ZipFile(zip_path, mode="w") as archive:
        archive.write(db_path, arcname="project/$DB_PATH")

    proc = subprocess.run(
        ["bash", "scripts/validate-release-zip.sh", str(zip_path)],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode != 0
    combined = proc.stdout + "\n" + proc.stderr
    assert "SQLite" in combined


def test_validator_rejects_sqlite_header_in_misleading_filename(tmp_path: Path):
    root = _repo_root()
    payload = tmp_path / "looks_like_text.txt"
    payload.write_bytes(b"SQLite format 3\x00payload")

    zip_path = tmp_path / "bad_release_nested.zip"
    with zipfile.ZipFile(zip_path, mode="w") as archive:
        archive.write(payload, arcname="project/nested/looks_like_text.txt")

    proc = subprocess.run(
        ["bash", "scripts/validate-release-zip.sh", str(zip_path)],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode != 0
    combined = proc.stdout + "\n" + proc.stderr
    assert "SQLite" in combined
