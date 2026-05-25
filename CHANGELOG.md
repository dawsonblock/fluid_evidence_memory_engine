# Changelog

## v0.8.4 — Extraction Span Accuracy Upgrade

- Improved support-span extraction accuracy for claim candidates.
- Added extraction span debugging output.
- Added span-alignment fixtures and regression tests.
- Preserved strict extractor fail-closed behavior.
- Preserved public/internal review-boundary behavior.
- Preserved retrieval quote-hit scoring.
- Preserved release-builder and release-validator behavior from v0.8.3.

## v0.8.3 — Release Builder Finalization

- Fixed `build-release-zip.sh` cleanup logic so it no longer combines `find -prune` with `-delete`.
- Added/updated release-builder regression tests.
- Preserved release ZIP validation for extensionless SQLite artifacts.
- Preserved v0.8.2 runtime-health migration completeness behavior.
- Preserved strict extractor fail-closed behavior.
- Preserved review-boundary and verify-boundary behavior.
- Preserved retrieval evaluation quote-hit scoring.

## v0.8.2 — Release Identity + Builder Reliability Repair

- Fixed release packaging to exclude accidental extensionless SQLite database files such as `$DB_PATH`.
- Updated the release validator to detect SQLite database artifacts by file content, not only file extension.
- Added structural archive validation for release ZIPs (empty/corrupt ZIPs now fail fast in both build and validator scripts).
- Added regression coverage for obvious database filenames and extensionless SQLite payloads in release ZIP validation.
- Added regression guards for runtime-health migration error timestamp reporting and retrieval support-quote sourcing from `claim_support_spans`.
- Preserved v0.8.1 migration reliability, runtime-health migration completeness checks, strict extractor fail-closed behavior, and public/internal review boundaries.
- Added extraction quality baseline documentation and a verbose extraction-eval mode for per-case diagnosis.
- Added mocked structured-extractor tests covering valid JSON, repair success/failure, quote mismatch rejection, and valid empty payloads.

## v0.8.1 — Test Harness + Migration Reliability Hardening

- Fixed source-ZIP test execution by making the local `tests` directory importable and using package-relative smoke-test imports.
- Added a non-Git fallback path to `scripts/build-release-zip.sh` so clean extracted source trees can rebuild release ZIPs.
- Added release-build regression coverage for both Git worktree and non-Git source-tree packaging paths.
- Made SQLite init strict by default for migration failures, with `FEME_LENIENT_INIT=true` as an explicit escape hatch.
- Added schema-meta tracking for migration failure state and timestamps instead of silently swallowing init-time migration exceptions.
- Added migration completeness checks for required schema effects and surfaced `migration_status`, `missing_schema_features`, and `last_migration_error` via runtime health.
- Preserved v0.8.0 structured extraction, retrieval evaluation, and embedding-provider behavior while hardening release/test reliability.

## v0.8.0 — Structured Extraction + Evaluation

- Realigned the public release identity to `0.8.0` across package, API, and schema reporting.
- Added structured claim extraction schema validation with strict fail-closed behavior for malformed payloads.
- Added an LLM JSON extractor provider shell and provider registry wiring.
- Split extraction semantics into `support_relation` and `evidence_kind` while preserving backward-compatible `evidence_relation` ingestion.
- Added an extractor repair loop for malformed structured output.
- Added extraction evaluation fixtures and baseline metrics via `feme eval-extraction`.
- Added retrieval evaluation CLI support via `feme eval-retrieval`.
- Added semantic embedding provider foundations with an optional sentence-transformers provider.
- Added embeddings rebuild support and embedding metadata columns for provider-aware rebuilds.
- Added PostgreSQL load and concurrency smoke test scaffolding alongside the live integration suite.
- Refreshed PostgreSQL proof artifact path for v0.8.0 at `docs/proof/postgres_v0_8_0.txt`.
- Preserved review-boundary behavior, extractor audit trails, and strict/public retrieval safety defaults.

## v0.7.6 — Release Hygiene + Postgres Proof Capture

- Cleaned release ZIP packaging: pre-cleanup removes `__pycache__`, `.pyc`, `.pyo`, `.egg-info`, `.DS_Store`, and `._*` before archiving.
- Added validation for macOS metadata artifacts (`__MACOSX/`, `._*`, `.DS_Store`) in `validate-release-zip.sh`.
- Added stricter release artifact checks for `.pyo`, `.ruff_cache`, `.mypy_cache`, `.sqlite`, `.db`, `.env`.
- Fixed release ZIP filename format to `fluid_evidence_memory_engine_v{VERSION}.zip`.
- Added `tests/test_strict_extractor_semantics.py` regression guard for strict extractor fail-closed behavior.
- Updated `docs/POSTGRES_PROOF.md` for v0.7.6 with `postgres_v0_7_6.txt` proof path.
- Preserved v0.7.5 strict extractor semantics and review boundary behavior.
- Bumped package/runtime/API metadata to `0.7.6`.

## v0.7.5 - Strict Extractor Semantics + Runtime Safety

- Fixed `json_strict` to fail closed when no structured extractor provider is configured or when structured output is invalid.
- Added extractor provider interface and runtime registry with built-in `json_static` and `llm_stub` providers.
- Added structured extractor metadata enrichment in `extractor_audit.metadata_json` (provider version, schema version, strict/fallback flags, error type, config hash).
- Added `FEME_REQUIRE_EXTRACTOR_AUDIT` policy to fail ingestion closed when extraction audit persistence is required and unavailable.
- Added CLI/API extractor schema version support and strict API behavior (`json_strict` missing provider returns 400 unless explicitly allowed evidence-only).
- Added strict/fallback extractor tests, audit failure mode tests, and provider registry tests.
- Added extraction quality fixture seeds plus `feme eval-extraction` command for baseline extraction evaluation.
- Added retrieval benchmark starter fixture and v0.7.5 PostgreSQL proof output placeholder artifact.
- Bumped package/runtime/schema metadata to `0.7.5`.

## v0.7.4 - Extractor Audit Persistence + Runtime Wiring

- Added durable extractor audit persistence via `extractor_audit` table (SQLite/PostgreSQL schema + migration).
- Wired `extractor_mode` and `extractor_provider` through API ingest endpoints, CLI ingest commands, and governed runtime ingestion pipeline.
- Added per-chunk extraction audit events capturing mode/provider, outcome, candidate count, and diagnostic detail.
- Preserved strict extractor semantics (`json_strict` fail-closed, fallback mode remains deterministic).
- Bumped package/runtime/schema metadata to `0.7.4`.

## v0.7.3 - Verification Boundary + Extractor Hardening

- Fixed `/verify` retrieval boundary leakage by wiring `retrieval_mode` and `include_pending_review` into verification context construction.
- Added explicit `publication_blocked` verification signal when pending-review claims/evidence are included in answer context.
- Hardened JSON claim extractor adapter to accept both `candidates` and `claims` payload keys.
- Enforced strict `support_quote_text` equality to the declared evidence char span.
- Rejected zero-length token spans in structured extractor payloads.
- Added regression tests for verify boundary defaults/publication blocking and JSON adapter strictness paths.
- Bumped package/runtime/schema metadata to `0.7.3`.

## v0.7.2 - Review Boundary Hardening

- Enforced strict pending-review filtering for chunk retrieval and context support evidence when `include_pending_review=false`.
- Added automatic `review_actions` audit row (`pending_created`) when claims are auto-created in `pending_review` due to `review_required` source policy.
- Added SQLite append-only ledger enforcement via update/delete triggers plus migration coverage.
- Added `scripts/build-release-zip.sh` to produce clean release ZIPs from git-tracked files only (prevents local cache/egg-info leakage).
- Added `feme ledger-verify --all-projects` and a no-events warning to avoid misleading zero-event project checks.
- Bumped package/runtime/schema version metadata to `0.7.2`.

## v0.7.1 - Auth Scope Hardening

- Added role-based API key scopes: viewer, reviewer, editor, admin.
- Added environment keys: `FEME_API_KEY_VIEWER`, `FEME_API_KEY_REVIEWER`, `FEME_API_KEY_EDITOR`, `FEME_API_KEY_ADMIN`.
- Preserved legacy compatibility for `FEME_API_KEY_READONLY` and `FEME_API_KEY` fallback behavior.
- Mapped endpoint protections by operation type:
  - viewer: read/query endpoints
  - reviewer: review queue endpoints
  - editor: ingest/governed mutations and evaluation writes
  - admin: backup, migrations, maintenance, retention redaction, source policy updates
- Expanded API auth tests to validate scope enforcement and no-auth legacy mode.
- Added token-level support offsets for exact claim support spans (`support_token_start`, `support_token_end`) during extraction and persistence.
- Expanded exact-span regression tests to verify token offsets are persisted and exposed in citations.
- Moved entity extraction and timeline generation into the same ingestion transaction as evidence/chunk writes.
- Added rollback regression coverage so timeline side-effect failures do not leave partial ingest artifacts.
- Added per-request API auth audit tracing for protected routes (method/path, required role, resolved role, decision, detail, principal hash).
- Added scaffold-level sentence-to-citation verification (`sentence_citation_checks`, `citation_verification`) so unsupported answer sentences are flagged before publication.
- Enforced strict pending-review filtering for chunk retrieval and context support evidence when `include_pending_review=false`.
- Added automatic `review_actions` audit row (`pending_created`) when claims are auto-created in `pending_review` due to `review_required` source policy.
- Added SQLite append-only ledger enforcement via update/delete triggers plus migration coverage.
- Added `scripts/build-release-zip.sh` to produce clean release ZIPs from git-tracked files only (prevents local cache/egg-info leakage).

## v0.7.0 - PostgreSQL Proof + Runtime Hygiene

- Fixed PostgreSQL dollar-quoted migration execution with robust SQL script splitting.
- Fixed source registry insertion counting with backend-neutral cursor rowcount semantics.
- Added live Postgres proof tests for migration/init, ingest, retrieval, ledger verification, append-only enforcement, dedup, source registry, native FTS path, and runtime health reporting.
- Added explicit PostgreSQL backup safety behavior (no silent SQLite backup path).
- Added release hygiene cleanup guidance and cache/artifact exclusions.
- Updated package/runtime/docs status to reflect verified dual-backend alpha behavior.

## v0.6.0 - PostgreSQL Runtime Backend

- Added runnable PostgreSQL backend selection through `FEME_DB_BACKEND=postgres`.
- Added `PostgresDatabase` facade and SQL compatibility translator.
- Rebuilt Postgres schema to mirror the current SQLite runtime tables.
- Updated CLI/API to use backend factory.
- Added Docker Compose Postgres API profile.
- Added Postgres SQL smoke command and tests.
- Validation: 23 tests passed, compile/import smoke checks run locally.

## v0.5.0 — Runtime hardening

- Added storage abstraction with `SQLiteStore`, `PostgresStore`, and explicit transaction helpers.
- Added idempotent migration manager and v0.5 runtime schema tables.
- Added append-only `memory_ledger` with hash-chain verification.
- Added governed ingestion pipeline with job tracking, claim writes, contradiction scanning, cluster rebuilds, and ledger events.
- Added deterministic claim canonicalization and `claim_clusters`.
- Added persistent retrieval evaluation cases and project-level eval-suite runner.
- Added runtime-health, migrate, ledger, governed-ingest, claim-cluster, and eval-suite CLI commands.
- Added FastAPI endpoints for the v0.5 runtime layer.
- Added v0.5 tests and smoke validation.

## v0.4.0

### Added

- Source registry with project-scoped source enable/disable controls.
- Source-quality overrides and review-required flags per source type.
- Timeline extraction from ISO and month-name dates into `timeline_events`.
- Citation builder that emits citation labels, quote snippets, span offsets, source titles, URIs, and hashes.
- Grounded answer scaffold generator.
- Memory capsules for subject-level consolidation without replacing underlying claims.
- Duplicate relationship creation for exact-normalized duplicate claims.
- Retention manager for local evidence redaction and project claim archiving.
- Maintenance manager for rebuilding full-text search rows and deterministic embeddings.
- API endpoints for sources, timeline, citations, answer scaffold, consolidation, capsules, retention, and maintenance.
- CLI commands for sources, timeline, citations, answer scaffold, consolidation, capsules, redaction, retention history, and maintenance.
- SQLite and PostgreSQL schema extensions for `source_registry`, `timeline_events`, `citation_records`, `memory_capsules`, and `retention_actions`.
- Expanded v0.4 tests.

### Fixed / improved

- Ingestion now checks source policy before accepting a source type.
- Ingestion now uses source-registry quality overrides when scoring chunks.
- Ingestion now records timeline events automatically.
- Project export includes v0.4 governance/citation/timeline/capsule/retention tables where available.
- API and package version bumped to v0.4.0.

### Validation

- `pytest`: 14 passed.
- `compileall`: passed.
- CLI/API import smoke test: passed.

### Still limited

- SQLite remains the tested runtime backend.
- PostgreSQL remains a schema target, not a completed adapter.
- Timeline extraction is regex-based.
- Answer generation remains intentionally conservative; the scaffold prepares grounded inputs but does not fabricate prose beyond the stored claims.

## v0.3.0

- Added project registry and project-scoped stats.
- Added ingestion job records.
- Added duplicate evidence suppression by SHA-256 per project.
- Added sensitivity detection/redaction helpers.
- Added review queue and review action history.
- Added provenance tracing for claim → evidence → token span.
- Added integrity checker and persisted integrity reports.
- Added SQLite backup manager.
- Added project import support.
- Added MMR-style retrieval diversification.
- Added context packet risk summaries.
- Added CLI/API commands for review, trace, backup, integrity, and project stats.

## v0.2.0

- Added entity extraction and `entity_mentions` persistence.
- Added exact `claim -> evidence -> token_span` links.
- Added evidence vault module for raw file preservation.
- Added memory policy thresholds and source-quality rules.
- Added lifecycle manager, answer/context verifier, project exporter, and retrieval evaluation harness.
- Fixed retrieval project isolation and package schema inclusion.
