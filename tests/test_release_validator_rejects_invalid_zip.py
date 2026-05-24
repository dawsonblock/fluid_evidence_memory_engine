from __future__ import annotations

import subprocess
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_validator_rejects_empty_zip(tmp_path: Path):
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
    assert "invalid release zip" in combined or "empty" in combined


def test_validator_rejects_corrupt_zip(tmp_path: Path):
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
    assert "integrity" in combined or "invalid" in combined