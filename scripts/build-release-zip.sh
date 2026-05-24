#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [[ $# -ge 1 ]]; then
	VERSION="$1"
else
	VERSION="$(awk '
		/^\[project\]/ { in_project=1; next }
		/^\[/ && in_project { in_project=0 }
		in_project && /^[[:space:]]*version[[:space:]]*=[[:space:]]*"[^"]+"/ {
			gsub(/^[^"]*"/, "", $0)
			gsub(/".*/, "", $0)
			print $0
			exit
		}
	' pyproject.toml)"
fi

if [[ -z "$VERSION" ]]; then
	echo "Unable to determine project version from pyproject.toml" >&2
	exit 2
fi

OUT_DIR="${OUT_DIR:-dist}"
VERSION_UNDERSCORED="${VERSION//./_}"
OUT_FILE="$OUT_DIR/fluid_evidence_memory_engine_v${VERSION_UNDERSCORED}.zip"

mkdir -p "$OUT_DIR"
rm -f "$OUT_FILE"

clean_runtime_databases() {
	find . \
		\( -path "./.git" -o -path "./.venv" -o -path "./venv" -o -path "./dist" -o -path "./build" \) -prune \
		-o \( \
			-name '$DB_PATH' \
			-o -name "*.sqlite" \
			-o -name "*.sqlite3" \
			-o -name "*.db" \
			-o -name "*.sqlite-journal" \
			-o -name "*.db-journal" \
			-o -name "*.sqlite-wal" \
			-o -name "*.sqlite-shm" \
			-o -name "*.db-wal" \
			-o -name "*.db-shm" \
		\) -type f -delete
}

# Pre-clean local caches so they are not accidentally staged.
chmod -R u+w .pytest_cache .ruff_cache .mypy_cache 2>/dev/null || true
rm -rf .pytest_cache .ruff_cache .mypy_cache || true
find . -name "__pycache__" -type d -prune -exec rm -rf {} +
find . -name "*.pyc" -delete
find . -name "*.pyo" -delete
find . -name ".DS_Store" -delete
find . -name "._*" -delete
rm -rf __MACOSX
clean_runtime_databases

if git rev-parse --is-inside-work-tree >/dev/null 2>&1 \
	&& [[ -z "$(git status --porcelain --untracked-files=normal)" ]]; then
	# Build from git-tracked content only so local caches/egg-info do not leak.
	# --worktree-attributes ensures local .gitattributes export-ignore rules apply.
	git archive --worktree-attributes --format=zip --output "$OUT_FILE" HEAD
else
	zip -r "$OUT_FILE" . \
		-x ".git/*" \
		-x "dist/*" \
		-x ".venv/*" \
		-x "venv/*" \
		-x "*__pycache__*" \
		-x "*.pyc" \
		-x "*.pyo" \
		-x "*.pytest_cache*" \
		-x "*.ruff_cache*" \
		-x "*.mypy_cache*" \
		-x "*.egg-info*" \
		-x "*__MACOSX*" \
		-x "*._*" \
		-x "*.DS_Store" \
		-x '$DB_PATH' \
		-x '*/$DB_PATH' \
		-x "memory.db" \
		-x "*.sqlite" \
		-x "*.sqlite3" \
		-x "*.db" \
		-x "*.sqlite-journal" \
		-x "*.db-journal" \
		-x "*.sqlite-wal" \
		-x "*.sqlite-shm" \
		-x "*.db-wal" \
		-x "*.db-shm" \
		-x "*.env"
fi

if [[ ! -s "$OUT_FILE" ]]; then
	echo "Release ZIP was not created or is empty: $OUT_FILE" >&2
	exit 1
fi

if ! python3 -m zipfile -t "$OUT_FILE" >/dev/null 2>&1; then
	echo "Release ZIP failed structural integrity check: $OUT_FILE" >&2
	exit 1
fi

echo "Created $OUT_FILE"
