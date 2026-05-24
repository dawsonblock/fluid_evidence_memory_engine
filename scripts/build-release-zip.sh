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

# Pre-clean local caches so they are not accidentally staged.
rm -rf .pytest_cache .ruff_cache .mypy_cache
find . -name "__pycache__" -type d -prune -exec rm -rf {} +
find . -name "*.pyc" -delete
find . -name "*.pyo" -delete
find . -name ".DS_Store" -delete
find . -name "._*" -delete
rm -rf __MACOSX

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
	# Build from git-tracked content only so local caches/egg-info do not leak.
	# --worktree-attributes ensures local .gitattributes export-ignore rules apply.
	git archive --worktree-attributes --format=zip --output "$OUT_FILE" HEAD
else
	zip -r "$OUT_FILE" . \
		-x ".git/*" \
		-x "dist/*" \
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
		-x "*.sqlite" \
		-x "*.db" \
		-x "*.env"
fi

echo "Created $OUT_FILE"
