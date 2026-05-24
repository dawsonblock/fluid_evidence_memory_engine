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

forbidden_pattern='egg-info/|__pycache__/|\.pyc$|\.pyo$|\.pytest_cache/|\.ruff_cache/|\.mypy_cache/|__MACOSX/|/\._|\.DS_Store|\.sqlite$|\.sqlite3$|\.db$|\.sqlite-journal$|\.db-journal$|\.sqlite-wal$|\.sqlite-shm$|\.db-wal$|\.db-shm$|\.env$'
if zipinfo -1 "$ZIP_PATH" | grep -E "$forbidden_pattern" >/dev/null; then
    echo "Forbidden artifacts found in release ZIP: $ZIP_PATH" >&2
    zipinfo -1 "$ZIP_PATH" | grep -E "$forbidden_pattern" >&2 || true
    exit 1
fi

obvious_db_names='(^|/)(\$DB_PATH|memory\.db|feme\.sqlite|feme\.db)$'
if zipinfo -1 "$ZIP_PATH" | grep -E "$obvious_db_names" >/dev/null; then
    echo "Forbidden SQLite database artifact names found in release ZIP: $ZIP_PATH" >&2
    zipinfo -1 "$ZIP_PATH" | grep -E "$obvious_db_names" >&2 || true
    exit 1
fi

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
unzip -q "$ZIP_PATH" -d "$tmpdir"

sqlite_hits=""
while IFS= read -r -d '' path; do
    if [[ "$(head -c 16 "$path" 2>/dev/null)" == "SQLite format 3" ]]; then
        sqlite_hits+="${path#$tmpdir/}"$'\n'
    fi
done < <(find "$tmpdir" -type f -print0)

if [[ -n "$sqlite_hits" ]]; then
    echo "Forbidden SQLite database artifact(s) found in release ZIP: $ZIP_PATH" >&2
    printf '%s' "$sqlite_hits" >&2
    exit 1
fi

echo "Release ZIP artifact check passed: $ZIP_PATH"