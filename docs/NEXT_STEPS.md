# Next Steps

## 1. Integrate a production structured extractor provider

v0.7.5 adds strict extractor semantics, provider registry wiring, and fail-closed behavior for `json_strict`.

Next step: plug in a production structured provider (LLM or rules engine) behind the provider registry while preserving current schema validation and audit metadata.

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

v0.7.5 ships extraction fixture seeds and `feme eval-extraction` for baseline extraction metrics; extend this into broader golden suites.

## 5. Strengthen PostgreSQL production readiness (post-v0.7)

v0.7 establishes a verified dual-backend alpha baseline with runnable Postgres runtime paths, live Docker-backed integration tests, and CI coverage.

Post-v0.7 priority gaps to close:

- high-concurrency ingestion and retrieval load testing
- broader adapter parity across all modules
- production backup/restore automation runbooks

## 6. Add stronger embeddings

v0.7.5 introduces an embedding provider interface/registry around hashing embeddings.

Next step: add semantic embedding providers (local or hosted) behind that interface and validate retrieval gains before enabling by default.

## Next hardening sequence

1. Port EvidenceIngestor, RetrievalPlanner, ReviewQueue, and RetentionManager onto the `MemoryStore` contract.
2. Expand PostgreSQL parity/load testing and preserve live proof artifacts in release evidence.
3. Add queue-backed ingestion workers for PDFs/HTML/legal XML/source snapshots.
4. Add auth-audit anomaly reporting (invalid-key spikes, denied-scope hotspots, unusual route access patterns).
5. Enforce citation-verification gates in downstream UI/publication workflows.
6. Add explicit retrieval modes (`internal` vs `public`) to control unreviewed evidence visibility policy.
