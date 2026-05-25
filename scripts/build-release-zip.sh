#!/usr/bin/env bash
# shellcheck disable=SC2016,SC2312
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT_DIR}"

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

if [[ -z ${VERSION} ]]; then
	echo "Unable to determine project version from pyproject.toml" >&2
	exit 2
fi

OUT_DIR="${OUT_DIR:-dist}"
VERSION_UNDERSCORED="${VERSION//./_}"
OUT_FILE="${OUT_DIR}/fluid_evidence_memory_engine_v${VERSION_UNDERSCORED}.zip"

BUILD_OK=0

cleanup_partial_zip() {
	if [[ ${BUILD_OK} -ne 1 ]]; then
		rm -f "${OUT_FILE}"
	fi
}

trap cleanup_partial_zip EXIT

mkdir -p "${OUT_DIR}"
rm -f "${OUT_FILE}"

clean_runtime_databases() {
	for pattern in '$DB_PATH' '*.sqlite' '*.sqlite3' '*.db' '*.sqlite-journal' '*.db-journal' '*.sqlite-wal' '*.sqlite-shm' '*.db-wal' '*.db-shm'; do
		find . -type f -name "${pattern}" \
			! -path "./.git/*" \
			! -path "./.venv/*" \
			! -path "./venv/*" \
			! -path "./dist/*" \
			! -path "./build/*" \
			-delete
	done
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

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
	# Build from git-tracked content only so local caches/egg-info do not leak.
	# --worktree-attributes ensures local .gitattributes export-ignore rules apply.
	git archive --worktree-attributes --format=zip --output "${OUT_FILE}" HEAD
else
	zip -r "${OUT_FILE}" . \
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

if [[ ! -s ${OUT_FILE} ]]; then
	echo "Release ZIP was not created or is empty: ${OUT_FILE}" >&2
	rm -f "${OUT_FILE}"
	exit 1
fi

if ! python3 -m zipfile -t "${OUT_FILE}" >/dev/null 2>&1; then
	echo "Release ZIP failed structural integrity check: ${OUT_FILE}" >&2
	rm -f "${OUT_FILE}"
	exit 1
fi

bash scripts/validate-release-zip.sh "${OUT_FILE}"

BUILD_OK=1

echo "Created ${OUT_FILE}"
