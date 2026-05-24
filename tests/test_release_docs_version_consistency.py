from __future__ import annotations

import re
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _project_version(root: Path) -> str:
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([0-9]+\.[0-9]+\.[0-9]+)"', text, re.MULTILINE)
    assert match, "project version not found in pyproject.toml"
    return match.group(1)


def test_release_docs_reference_current_version_consistently():
    root = _repo_root()
    version = _project_version(root)
    version_us = version.replace(".", "_")

    readme = (root / "README.md").read_text(encoding="utf-8")
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    proof_doc = (root / "docs" / "POSTGRES_PROOF.md").read_text(encoding="utf-8")

    assert f"FEME v{version}" in readme
    assert f"## v{version}" in changelog
    assert f"FEME v{version}" in proof_doc
    assert f"docs/proof/postgres_v{version_us}.txt" in proof_doc
    assert "dist/fluid_evidence_memory_engine_v*.zip" in readme