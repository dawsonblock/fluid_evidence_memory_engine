#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VENV_DIR="${VENV_DIR:-.venv}"
POSTGRES_DSN="${FEME_POSTGRES_DSN:-postgresql://feme:feme_dev_password@localhost:5432/feme}"
KEEP_POSTGRES="${KEEP_POSTGRES:-0}"
SKIP_SETUP="${SKIP_SETUP:-0}"

if [[ "$SKIP_SETUP" != "1" ]]; then
    bash scripts/dev-setup.sh
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    echo "Missing virtual environment interpreter at $VENV_DIR/bin/python" >&2
    echo "Run: bash scripts/dev-setup.sh" >&2
    exit 1
fi

docker compose --profile postgres up -d postgres

cleanup() {
    if [[ "$KEEP_POSTGRES" != "1" ]]; then
        docker compose --profile postgres down >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

export FEME_DB_BACKEND=postgres
export FEME_POSTGRES_DSN="$POSTGRES_DSN"
export FEME_TEST_POSTGRES_DSN="$POSTGRES_DSN"

"$VENV_DIR/bin/python" -m pytest -q tests/test_v07_postgres_live_integration.py

echo
printf '%s\n' "PostgreSQL proof checks passed." "DSN: $POSTGRES_DSN"
if [[ "$KEEP_POSTGRES" == "1" ]]; then
    echo "Postgres container left running (KEEP_POSTGRES=1)."
fi
