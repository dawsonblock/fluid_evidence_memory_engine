from __future__ import annotations

import shutil
import subprocess
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


@pytest.mark.skipif(not _has_git(), reason="git is required for release script regression check")
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
