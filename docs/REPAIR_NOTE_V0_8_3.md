# FEME v0.8.3 Repair Note

Date: 2026-05-24
Repository: fluid_evidence_memory_engine
Branch: main
Head commit: a3c6cbe

## Scope

This note records the gap between issues observed in the previously analyzed v0.8.0 release ZIP and the current, fixed state on main for v0.8.3.

## Summary

- The major release-builder and archive-validation issues reported against the old v0.8.0 ZIP are addressed on main.
- Current local verification remains green for the full test suite and trunk checks.
- Postgres smoke tests are environment-dependent and require a valid DSN.

## Issue To Fix Mapping

| Old v0.8.0 finding | v0.8.3 state on main |
| --- | --- |
| Release ZIP build path could produce invalid or incomplete archives in edge paths | Release builder script now includes stricter build flow, non-empty ZIP checks, and structural verification before acceptance |
| Archive validation did not fully guard against invalid/corrupt or forbidden-content archives | Release validator now enforces empty/corrupt rejection, forbidden artifact pattern checks, and SQLite magic-header detection in extracted files |
| Migration/runtime reliability gaps under strict initialization and backend-specific migrations | Migration execution is backend-guarded and idempotent; runtime records migration failures and surfaces health metadata for strict diagnostics |
| Script-level test expectations brittle to shell formatter normalization | Script tests were hardened to accept equivalent normalized forms rather than single text shape |
| General lint/security/tooling debt around release hardening | Repository is currently passing trunk checks on main |

## Primary Files Carrying The Fixes

- scripts/build-release-zip.sh
- scripts/validate-release-zip.sh
- src/feme/db.py
- src/feme/migrations.py
- src/feme/migration_health.py
- src/feme/runtime.py
- tests/test_release_build_script.py
- tests/test_test_runner_scripts.py

## Verification Snapshot

Latest verification run context on main:

```text
git log -1 --oneline
a3c6cbe (HEAD -> main, origin/main, origin/HEAD) Finalize v0.8.3 release hardening and cleanup

pytest -q
301 passed, 3 skipped

trunk check --all
Checked 168 files
No issues
```

## Notes

- Postgres smoke tests are expected to fail or skip when DSN environment variables are unset or invalid.
- This document is an audit-style repair summary and does not replace versioned upgrade notes.