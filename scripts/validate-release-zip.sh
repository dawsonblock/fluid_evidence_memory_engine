#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <zip-path>" >&2
    exit 2
fi

ZIP_PATH="$1"
if [[ ! -f "$ZIP_PATH" ]]; then
    echo "ZIP not found: $ZIP_PATH" >&2
    exit 2
fi

forbidden_pattern='egg-info/|__pycache__/|\.pyc$|\.pyo$|\.pytest_cache/|\.ruff_cache/|\.mypy_cache/|__MACOSX/|/\._|\.DS_Store|\.sqlite$|\.db$|\.env$'
if zipinfo -1 "$ZIP_PATH" | grep -E "$forbidden_pattern" >/dev/null; then
    echo "Forbidden artifacts found in release ZIP: $ZIP_PATH" >&2
    zipinfo -1 "$ZIP_PATH" | grep -E "$forbidden_pattern" >&2 || true
    exit 1
fi

echo "Release ZIP artifact check passed: $ZIP_PATH"