from __future__ import annotations

from pathlib import Path

import pytest

from feme.answer_builder import GroundedAnswerBuilder
from feme.claim_extractor import extract_candidates_for_evidence
from feme.consolidation import MemoryConsolidator
from feme.db import Database
from feme.evidence import EvidenceIngestor
from feme.retention import REDACTION_TEXT, RetentionManager
from feme.source_registry import SourceRegistry
from feme.temporal import TimelineManager
from feme.write_governor import MemoryWriteGovernor


def _db(tmp_path: Path) -> Database:
    db = Database(str(tmp_path / "test.sqlite"))
    db.init()
    return db


def test_source_registry_can_disable_source_type(tmp_path: Path):
    db = _db(tmp_path)
    reg = SourceRegistry(db)
    reg.upsert("note", enabled=False)
    with pytest.raises(ValueError):
        EvidenceIngestor(db).ingest_text("Use PostgreSQL as canonical memory on 2026-05-22.", source_type="note")
    reg.upsert("note", enabled=True, default_quality=0.77)
    result = EvidenceIngestor(db).ingest_text("Use PostgreSQL as canonical memory on 2026-05-22.", source_type="note")
    assert result["evidence_id"].startswith("ev_")


def test_timeline_citations_and_answer_scaffold(tmp_path: Path):
    db = _db(tmp_path)
    result = EvidenceIngestor(db).ingest_text(
        "Use PostgreSQL as canonical memory. The review happened on March 4, 2024.",
        source_type="official_record",
        title="timeline sample",
    )
    candidates = extract_candidates_for_evidence(db, result["evidence_id"])
    assert candidates
    gov = MemoryWriteGovernor(db)
    for c in candidates:
        gov.commit_candidate(c)
    timeline = TimelineManager(db).list()
    assert any(t["event_date"] == "2024-03-04" for t in timeline)
    scaffold = GroundedAnswerBuilder(db).build_scaffold("What database should memory use?")
    assert scaffold["citations"]
    assert scaffold["claims"]
    assert scaffold["risk_summary"]["risk"] in {"low", "medium", "high"}


def test_consolidation_capsules_and_retention_redaction(tmp_path: Path):
    db = _db(tmp_path)
    text = "Memory system should use PostgreSQL. Memory system should link claims to spans. Memory system should preserve evidence."
    result = EvidenceIngestor(db).ingest_text(text, source_type="official_record")
    gov = MemoryWriteGovernor(db)
    for c in extract_candidates_for_evidence(db, result["evidence_id"]):
        gov.commit_candidate(c)
    consolidation = MemoryConsolidator(db).create_subject_capsules(min_claims=1)
    assert consolidation["capsules_created"] >= 1
    redaction = RetentionManager(db).redact_evidence(result["evidence_id"], reason="test")
    assert redaction["redacted"] is True
    with db.connect() as con:
        span = con.execute("SELECT text FROM token_spans WHERE evidence_id = ? LIMIT 1", (result["evidence_id"],)).fetchone()
        assert span["text"] == REDACTION_TEXT
        archived = con.execute("SELECT COUNT(*) AS n FROM memory_claims WHERE status = 'archived'").fetchone()["n"]
        assert archived >= 1
