from __future__ import annotations

from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_release_hardening_script_prefers_project_venv_python():
    root = _repo_root()
    text = (root / "scripts" / "test-release-hardening.sh").read_text(encoding="utf-8")

    assert 'PYTHON_BIN="python"' in text
    assert 'if [[ -x ".venv/bin/python" ]]; then' in text
    assert 'PYTHON_BIN=".venv/bin/python"' in text
    assert '"$PYTHON_BIN" -m pytest -q' in text


def test_test_all_script_prefers_project_venv_python():
    root = _repo_root()
    text = (root / "scripts" / "test-all.sh").read_text(encoding="utf-8")

    assert 'PYTHON_BIN="python"' in text
    assert 'if [[ -x ".venv/bin/python" ]]; then' in text
    assert 'PYTHON_BIN=".venv/bin/python"' in text
    assert '"$PYTHON_BIN" -m pytest -q' in text