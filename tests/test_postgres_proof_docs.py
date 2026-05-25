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


def test_postgres_proof_doc_references_versioned_artifact():
    root = _repo_root()
    version = _project_version(root)
    expected = f"docs/proof/postgres_v{version.replace('.', '_')}.txt"

    doc_text = (root / "docs" / "POSTGRES_PROOF.md").read_text(encoding="utf-8")

    assert expected in doc_text
    assert "postgres_v0_7_6.txt" not in doc_text


def test_versioned_postgres_proof_artifact_exists():
    root = _repo_root()
    version = _project_version(root)
    artifact = root / "docs" / "proof" / f"postgres_v{version.replace('.', '_')}.txt"

    assert artifact.exists(), f"missing proof artifact: {artifact}"
    text = artifact.read_text(encoding="utf-8")
    lowered = text.lower()
    assert (
        "passed" in lowered
        or "external proof capture has not yet been run" in lowered
    )
