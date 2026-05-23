# MemoryStore Target (Deferred)

This document defines the target backend-neutral contract for a future full MemoryStore migration.

Status in v0.7.5:

- Deferred by design.
- The current `PostgresDatabase` facade remains acceptable for alpha dual-backend behavior.

## Why deferred

v0.7.5 prioritizes strict extractor semantics and runtime safety over large architecture churn.

The full MemoryStore migration is planned for v0.9/v1.0 hardening.

## Candidate modules to migrate later

- `EvidenceIngestor`
- `RetrievalPlanner`
- `WriteGovernor`
- `SourceRegistry`
- `ReviewQueue`
- `RetentionManager`
- `Ledger`
- `CitationBuilder`
- `ContextBuilder`

## Target interface

```python
class MemoryStore:
    def create_evidence(...): ...
    def create_chunks(...): ...
    def create_claims(...): ...
    def search_claims(...): ...
    def search_chunks(...): ...
    def append_ledger(...): ...
    def trace_claim(...): ...
    def list_pending_review(...): ...
```

## Migration notes

- Keep behavior parity and existing audit invariants while incrementally porting modules.
- Preserve SQLite/PostgreSQL compatibility through adapter-backed integration tests.
- Keep claim support span and extraction audit semantics stable during the refactor.
