#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RECREATE_VENV="${RECREATE_VENV:-0}"
PYTHON_BIN="${PYTHON_BIN:-}"
VENV_DIR="${VENV_DIR:-.venv}"
EDITABLE_INSTALL="${EDITABLE_INSTALL:-1}"

choose_python() {
    if [[ -n "$PYTHON_BIN" ]]; then
        echo "$PYTHON_BIN"
        return
    fi

    if command -v python3.10 >/dev/null 2>&1; then
        echo "python3.10"
        return
    fi

    if command -v python3 >/dev/null 2>&1; then
        echo "python3"
        return
    fi

    echo "No suitable Python interpreter found. Install Python 3.10+." >&2
    exit 1
}

PY="$(choose_python)"

if ! "$PY" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
    echo "Selected interpreter '$PY' is below Python 3.10." >&2
    "$PY" --version >&2 || true
    exit 1
fi

if [[ "$RECREATE_VENV" == "1" && -d "$VENV_DIR" ]]; then
    rm -rf "$VENV_DIR"
fi

if [[ ! -d "$VENV_DIR" ]]; then
    "$PY" -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel
if [[ "$EDITABLE_INSTALL" == "1" ]]; then
    "$VENV_DIR/bin/python" -m pip install -e '.[dev,api,postgres,tokenizers]'
else
    "$VENV_DIR/bin/python" -m pip install '.[dev,api,postgres,tokenizers]'
fi

echo
echo "Environment ready."
echo "Interpreter: $($VENV_DIR/bin/python -c 'import sys; print(sys.executable)')"
echo "Python: $($VENV_DIR/bin/python --version)"
echo
echo "Activate with: source $VENV_DIR/bin/activate"
