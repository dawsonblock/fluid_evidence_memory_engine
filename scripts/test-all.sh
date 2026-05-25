#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT_DIR}"

PYTHON_BIN="python"
if [[ -x ".venv/bin/python" ]]; then
	PYTHON_BIN=".venv/bin/python"
fi

echo "[1/2] Running release hardening smoke suite"
bash scripts/test-release-hardening.sh

echo "[2/2] Running full pytest suite"
"${PYTHON_BIN}" -m pytest -q
