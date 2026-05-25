from __future__ import annotations

import re
import subprocess
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _project_version(root: Path) -> str:
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"', text, re.MULTILINE)
    assert match, "project version not found in pyproject.toml"
    return match.group(1)


def test_build_release_zip_uses_project_version_in_filename():
    root = _repo_root()
    version = _project_version(root)
    expected = (
        root / "dist" / f"fluid_evidence_memory_engine_v{version.replace('.', '_')}.zip"
    )

    subprocess.run(["bash", "scripts/build-release-zip.sh"], cwd=root, check=True)

    assert expected.exists(), f"expected release archive missing: {expected}"
