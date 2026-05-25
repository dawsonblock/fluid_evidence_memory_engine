# v0.7.5 Upgrade: Strict Extractor Semantics + Runtime Safety

v0.7.5 hardens the extraction pipeline with fail-closed `json_strict` behavior, a pluggable provider registry, enriched audit metadata, and an evaluation harness for extraction quality.

## Main changes

Note for newer releases: v0.8.0 keeps `claim-extraction-v1` but separates support/link semantics from derivation semantics (`support_relation` + `evidence_kind`) while still accepting legacy `evidence_relation` payloads.

- `json_strict` now fails closed when no structured extractor provider is configured or when structured output is invalid — no silent fallback to heuristic extraction.
- Added extractor provider interface (`ExtractorProvider` Protocol) and `ExtractorRegistry` with built-in `json_static` and `llm_stub` providers in `src/feme/extractors/`.
- Extended `extractor_audit.metadata_json` to capture: `provider_name`, `provider_version`, `schema_version`, `strict_mode`, `fallback_used`, `error_type`, `config_hash`.
- Added `FEME_REQUIRE_EXTRACTOR_AUDIT` policy: when `true`, ingestion fails closed if extraction audit persistence is unavailable (raises `ExtractorAuditWriteError`).
- Added `--extractor-schema-version` option to `ingest-text`, `ingest-governed`, and the new `eval-extraction` CLI command.
- Added extraction quality fixture seeds (`tests/fixtures/extraction/`) and `feme eval-extraction` command for baseline extraction metric reporting.
- Added retrieval benchmark starter fixture (`tests/fixtures/retrieval/basic_memory_cases.jsonl`).
- Added embedding provider interface (`EmbeddingProvider` Protocol), `EmbeddingRegistry`, and `HashingEmbeddingProvider` in `src/feme/embeddings.py`.
- Updated `docs/MEMORYSTORE_TARGET.md` with v0.7.5 deferred status and planned migration scope.

## New environment variables

| Variable                        | Default               | Purpose                                                       |
| ------------------------------- | --------------------- | ------------------------------------------------------------- |
| `FEME_REQUIRE_EXTRACTOR_AUDIT`  | `false`               | Fail ingestion closed when extraction audit persistence fails |
| `FEME_EXTRACTOR_SCHEMA_VERSION` | `claim-extraction-v1` | Schema version tag written to `extractor_audit.metadata_json` |

Variables from v0.7.4 that remain unchanged:

| Variable                  | Notes                                                |
| ------------------------- | ---------------------------------------------------- |
| `FEME_EXTRACTOR_MODE`     | `heuristic` / `json_with_fallback` / `json_strict`   |
| `FEME_EXTRACTOR_PROVIDER` | Provider label resolved against the runtime registry |

## No schema migration required

All `extractor_audit` columns introduced in v0.7.4 are already in the migration chain. v0.7.5 only adds richer values written to the existing `metadata_json` column — no new columns or tables.

Run `feme migrate` after upgrading to ensure all prior migrations are applied:

```bash
feme migrate
```

## Install

```bash
pip install -e '.[api,postgres]'
```

## Verify fail-closed behavior

```bash
# json_strict with a missing provider should reject without persisting claims
feme ingest-text \
  --text "FEME must use strict extraction." \
  --extractor-mode json_strict \
  --extractor-provider missing-provider
```

Expected: no claim rows written; audit record shows `status=strict_rejected`.

## Run extraction evaluation

```bash
feme eval-extraction --fixture tests/fixtures/extraction/project_decisions.jsonl
```

Returns a JSON report with `claim_count_accuracy`, `support_span_exact_match`, `quote_exact_match`, `strict_rejection_rate`, and `fallback_rate`.

## Audit failure policy

Set `FEME_REQUIRE_EXTRACTOR_AUDIT=true` to enforce hard failure when the audit row cannot be written:

```bash
FEME_REQUIRE_EXTRACTOR_AUDIT=true feme ingest-text --text "..." --extractor-mode json_with_fallback
```

## Deferred: MemoryStore migration

The full backend-neutral `MemoryStore` contract migration remains deferred to v0.9/v1.0. See `docs/MEMORYSTORE_TARGET.md` for candidate modules and the target interface.

## Test coverage

New tests added in v0.7.5:

- `tests/test_extractor_modes.py` — strict/fallback mode behavior
- `tests/test_extractor_audit_failure_modes.py` — fail-closed audit enforcement
- `tests/test_extractor_audit.py` — audit record metadata
- `tests/test_extractor_provider_registry.py` — provider registration and default registry
- `tests/test_claim_extractor_json_adapter.py` — JSON adapter strictness paths
- `tests/test_extraction_eval.py` — extraction eval fixture runner
- `tests/test_embeddings_capabilities.py` — embedding provider and pgvector probe
