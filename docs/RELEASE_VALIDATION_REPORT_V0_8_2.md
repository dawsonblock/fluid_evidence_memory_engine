# FEME v0.8.2 Release Validation Report

Date: 2026-05-24
Scope: Release identity + builder reliability repair checklist verification

## Summary

FEME v0.8.2 release-hardening checks passed for:

- version identity coherence (package/runtime/schema/docs)
- source-ZIP-compatible release build path
- release ZIP structural and content validation
- runtime-health migration completeness reporting
- retrieval quote-hit scoring against support spans
- strict extractor and review-boundary governance behavior

## Validation Results

### 1. Compile

Command:

```bash
PYTHONPATH="$(pwd):src" .venv/bin/python -m compileall src tests
```

Result: Passed.

### 2. Full test suite

Command:

```bash
PYTHONPATH="$(pwd):src" .venv/bin/python -m pytest -q
```

Result: `286 passed, 12 skipped`.

### 3. Release build + validator

Commands:

```bash
bash scripts/build-release-zip.sh
bash scripts/validate-release-zip.sh dist/fluid_evidence_memory_engine_v0_8_2.zip
```

Result: Passed.

Artifact:

- `dist/fluid_evidence_memory_engine_v0_8_2.zip`
- Size observed during validation: ~9.6 MB

### 4. Explicit DB filename leak scan

Command:

```bash
zipinfo -1 dist/fluid_evidence_memory_engine_v0_8_2.zip | grep -E '\$DB_PATH|\.sqlite|\.sqlite3|\.db$|sqlite-wal|sqlite-shm|db-wal|db-shm'
```

Result: No matches.

### 5. Content-based SQLite payload scan

Command:

```bash
tmpdir=$(mktemp -d)
unzip -q dist/fluid_evidence_memory_engine_v0_8_2.zip -d "$tmpdir"
find "$tmpdir" -type f -exec sh -c '
  for f do
    if [ "$(head -c 16 "$f" 2>/dev/null)" = "SQLite format 3" ]; then
      echo "SQLite artifact found: $f"
      exit 1
    fi
  done
' sh {} +
```

Result: No SQLite content artifacts found.

### 6. SQLite runtime smoke

Commands:

```bash
tmpdir=$(mktemp -d)
export FEME_DB_PATH="$tmpdir/feme.sqlite"
.venv/bin/feme init
.venv/bin/feme runtime-health
```

Result fields:

- `package_version`: `0.8.2`
- `schema_version`: `0.8.2`
- `migration_status`: `complete`
- `missing_schema_features`: `[]`
- `last_migration_error`: `null`

### 7. Eval smoke

Commands:

```bash
.venv/bin/feme eval-extraction --fixture tests/fixtures/extraction/project_decisions.jsonl
.venv/bin/feme eval-retrieval --fixture tests/fixtures/retrieval/basic_memory_cases.jsonl
```

Result highlights:

- eval-extraction command ran successfully
- retrieval metrics:
  - `claim_found_rate`: `1.0`
  - `quote_hit_rate`: `1.0`
  - `pending_review_leak_rate`: `0.0`

### 8. Governance behavior smoke

Commands exercised:

- strict extractor fail-closed ingest (`--extractor-mode json_strict`)
- review-required source policy ingest
- public/internal search boundary checks
- public/internal verify boundary checks

Result highlights:

- strict mode produced no claim writes for unavailable structured extraction path
- public verify remained publication-safe (`publication_blocked=false`)
- internal verify correctly blocked publication when pending-review material included (`publication_blocked=true`)

## Release Notes Alignment

Additional named regression tests included in this cycle:

- `tests/test_release_validator_rejects_invalid_zip.py`
- `tests/test_retrieval_eval_quote_support_spans.py`

Changelog v0.8.2 heading aligned to release framing:

- `v0.8.2 — Release Identity + Builder Reliability Repair`

## Known Boundaries

- Postgres proof remains Docker-backed smoke/integration evidence, not high-scale production performance proof.
- Optional semantic dependencies may skip related tests when unavailable, by design.
