#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT_DIR}"

PYTHON_BIN="python"
if [[ -x ".venv/bin/python" ]]; then
	PYTHON_BIN=".venv/bin/python"
fi

# Placeholder DSN keeps smoke tests in explicit skip mode when no live DB is configured.
export FEME_DB="${FEME_DB:-postgresql://USER:PASSWORD@HOST:5432/DBNAME}"

"${PYTHON_BIN}" -m pytest -q \
	tests/test_release_build_script.py \
	tests/test_release_zip_version_naming.py \
	tests/test_release_zip_forbidden_artifacts.py \
	tests/test_release_zip_validator_negative.py \
	tests/test_release_docs_version_consistency.py \
	tests/test_postgres_proof_docs.py \
	tests/test_postgres_load_smoke.py \
	tests/test_postgres_concurrency_smoke.py
