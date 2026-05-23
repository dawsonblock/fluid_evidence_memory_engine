#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

VERSION="${1:-$(python3 -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")}" 
OUT_DIR="${OUT_DIR:-dist}"
OUT_FILE="$OUT_DIR/fluid_evidence_memory_engine-v${VERSION}.zip"

mkdir -p "$OUT_DIR"
rm -f "$OUT_FILE"

# Build from git-tracked content only so local caches/egg-info do not leak.
git archive --format=zip --output "$OUT_FILE" HEAD

echo "Created $OUT_FILE"
