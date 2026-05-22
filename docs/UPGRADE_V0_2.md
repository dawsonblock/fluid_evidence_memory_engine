# v0.2 Upgrade Notes

## Main improvement

v0.2 converts the starter from a basic claim-memory skeleton into a more auditable memory runtime.

The most important fix is exact span linkage:

```text
claim -> claim_evidence_links -> token_spans -> evidence_snapshots
```

This lets a generated context packet carry not only a remembered claim, but the exact source span that created it.

## New modules

```text
policy.py            configurable save thresholds and source quality rules
entity_extractor.py  lightweight entity and mention extraction
evidence_vault.py    raw file vault
lifecycle.py         salience decay and stale marking
verifier.py          grounding/risk checks
export_import.py     project export
evaluation.py        retrieval evaluation harness
```

## New CLI commands

```bash
feme list-entities --db memory.db
feme verify --db memory.db "question"
feme run-decay --db memory.db --project-id memory
feme export-project --db memory.db --project-id memory --out export.json
feme eval-case --db memory.db "query" --expected-term PostgreSQL
feme audit --db memory.db
```

## Database changes

Added tables:

```text
entity_mentions
lifecycle_events
evaluation_runs
```

Added indexes for project evidence lookup, entity mentions, and lifecycle events.

## Known migration note

Calling `feme init --db existing.db` is safe for adding new tables because the schema uses `CREATE TABLE IF NOT EXISTS`. It will not rewrite old rows or backfill entity mentions for old chunks. To backfill old data, re-ingest or add a dedicated backfill command later.
