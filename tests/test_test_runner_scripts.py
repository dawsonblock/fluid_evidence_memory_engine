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
    assert (
        '"$PYTHON_BIN" -m pytest -q' in text or '"${PYTHON_BIN}" -m pytest -q' in text
    )


def test_test_all_script_prefers_project_venv_python():
    root = _repo_root()
    text = (root / "scripts" / "test-all.sh").read_text(encoding="utf-8")

    assert 'PYTHON_BIN="python"' in text
    assert 'if [[ -x ".venv/bin/python" ]]; then' in text
    assert 'PYTHON_BIN=".venv/bin/python"' in text
    assert (
        '"$PYTHON_BIN" -m pytest -q' in text or '"${PYTHON_BIN}" -m pytest -q' in text
    )


def test_postgres_proof_script_requires_and_uses_virtualenv_python():
    root = _repo_root()
    text = (root / "scripts" / "postgres-proof.sh").read_text(encoding="utf-8")

    assert 'VENV_DIR="${VENV_DIR:-.venv}"' in text
    assert (
        'if [[ ! -x "$VENV_DIR/bin/python" ]]; then' in text
        or 'if [[ ! -x "${VENV_DIR}/bin/python" ]]; then' in text
    )
    assert (
        'echo "Missing virtual environment interpreter at $VENV_DIR/bin/python" >&2'
        in text
        or 'echo "Missing virtual environment interpreter at ${VENV_DIR}/bin/python" >&2'
        in text
    )
    assert 'EDITABLE_INSTALL="${EDITABLE_INSTALL:-0}" bash scripts/dev-setup.sh' in text
    assert (
        '"$VENV_DIR/bin/python" -m pytest -q tests/test_v07_postgres_live_integration.py'
        in text
        or '"${VENV_DIR}/bin/python" -m pytest -q tests/test_v07_postgres_live_integration.py'
        in text
    )


def test_dev_setup_supports_non_editable_install_toggle():
    root = _repo_root()
    text = (root / "scripts" / "dev-setup.sh").read_text(encoding="utf-8")

    assert 'EDITABLE_INSTALL="${EDITABLE_INSTALL:-1}"' in text
    assert (
        'if [[ "$EDITABLE_INSTALL" == "1" ]]; then' in text
        or 'if [[ $EDITABLE_INSTALL == "1" ]]; then' in text
        or 'if [[ ${EDITABLE_INSTALL} == "1" ]]; then' in text
    )
    assert "-m pip install -e '.[dev,api,postgres,tokenizers]'" in text
    assert "-m pip install '.[dev,api,postgres,tokenizers]'" in text
