# Architecture

## Invariants

1. Evidence is immutable at the memory layer.
2. Claims are mutable interpretations linked to evidence.
3. Summaries do not become authority.
4. Decay lowers salience, not truth.
5. Contradictions create state transitions, not silent overwrites.
6. Every answer should be reconstructable from claims and source spans.
7. Project memory is isolated by `project_id`.

## Core data objects

### Evidence source

Raw source metadata with SHA-256 hash, title, source URI, source type, review status, project ID, and metadata.

### Evidence snapshot

The extracted text snapshot for a source. This lets the system preserve what was indexed at ingestion time.

### Text chunk

Retrieval-oriented slice of evidence with character and token offsets.

### Token span

Exact anchor back into source text. Claims link to token spans through `claim_evidence_links`.

### Entity and entity mention

A simple normalized entity registry with mentions linked to evidence/chunks/spans.

### Memory claim

Structured memory unit with subject, predicate, object, claim text, confidence, salience, source quality, status, and temporal validity fields.

### Contradiction

A durable record that two claims conflict.

### Lifecycle event

Audit trail for decay, stale marking, and supersession.

## Save policy

The system first extracts candidate memories, then routes them through the Memory Write Governor.

A candidate is saved only when it is durable, useful, evidence-linked, explicit, contradictory, or project-relevant enough to pass policy.

## Retrieval policy

Retrieval uses claims first, chunks second. Vector similarity is never the only signal. Full-text match, confidence, source quality, salience, status, and contradiction state all affect ranking.

## Verification policy

The verifier checks context packets for:

- unsupported claims
- disputed/superseded/rejected/stale claim states
- missing evidence IDs
- missing span links
- warning propagation

It does not prove claims true; it exposes grounding risk.
