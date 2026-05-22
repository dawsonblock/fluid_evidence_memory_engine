# v0.4 Upgrade Notes

v0.4 adds operational controls around the v0.3 evidence memory core. The main theme is moving from storage/retrieval toward governed use: source admission, timeline construction, citation packets, answer scaffolds, consolidation, retention, and maintenance.

## New modules

```text
source_registry.py   Source allow/deny controls and quality overrides
temporal.py          Date extraction and project timeline management
citations.py         Citation packets from context evidence spans
answer_builder.py    Grounded answer scaffold generator
consolidation.py     Memory capsules and duplicate relationship creation
retention.py         Evidence redaction and claim archiving
maintenance.py       FTS/embedding rebuild and vacuum utilities
```

## New tables

```text
source_registry
timeline_events
citation_records
memory_capsules
retention_actions
```

## Why these matter

Source registry prevents bad or disabled source classes from entering the memory system without explicit policy. Timeline events let legal/case/project memory be queried chronologically. Citation records convert retrieved spans into stable, auditable answer references. Capsules compress repeated subject-level claims without becoming authority. Retention actions let local text be redacted or archived while keeping an audit trail.

## Accuracy stance

Capsules, answer scaffolds, and citations are derivative. Raw evidence snapshots and token spans remain authoritative. Redaction is local data minimization and does not certify that external copies or backups have been deleted.
