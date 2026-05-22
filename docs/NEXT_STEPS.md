# Next Steps

## 1. Add real extraction model

Current extraction is heuristic. Replace with a strict JSON LLM adapter:

```json
{
  "claims": [
    {
      "subject": "...",
      "predicate": "...",
      "object": "...",
      "claim_text": "...",
      "memory_type": "project_decision",
      "confidence": 0.0,
      "evidence_span": {"char_start": 0, "char_end": 0}
    }
  ]
}
```

The adapter must never write directly. It should propose candidates, then the Memory Write Governor decides.

## 2. Add review UI

Required screens:

- pending claims
- contradictions
- source registry
- claim merge/supersede decisions
- answer audit playback
- evidence span viewer

## 3. Add adapters

- PDF parser
- email parser
- HTML snapshotter
- code repo parser
- legal XML parser
- CSV/statistics parser

## 4. Expand evaluation harness

Test cases should cover:

- recall accuracy
- contradiction detection
- stale claim suppression
- unsupported answer rejection
- source-span accuracy
- token-budget packing efficiency
- project isolation

## 5. Complete PostgreSQL parity and live CI

v0.6 added a runnable PostgreSQL runtime path (`FEME_DB_BACKEND=postgres` and `FEME_POSTGRES_DSN`), but it is not production-proven yet.

Priority gaps to close:

- live Postgres integration test suite in CI
- native Postgres full-text search and ranking path
- stronger transaction and concurrency proof coverage

## 6. Add stronger embeddings

The hashing embedder is deterministic and offline, but weak. Replace with a local sentence-transformer, OpenAI embeddings, or another embedding model behind an adapter.


## After v0.5

1. Port EvidenceIngestor, RetrievalPlanner, ReviewQueue, and RetentionManager onto the `MemoryStore` contract.
2. Add real PostgreSQL integration tests using docker-compose and the postgres optional dependency.
3. Add queue-backed ingestion workers for PDFs/HTML/legal XML/source snapshots.
4. Add authenticated API roles for viewer/reviewer/editor/admin.
5. Add per-answer sentence-to-citation verification before any public output layer.
