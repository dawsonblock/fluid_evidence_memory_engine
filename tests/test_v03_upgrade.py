from pathlib import Path

from feme.backup import BackupManager
from feme.claim_extractor import extract_candidates_for_evidence
from feme.db import Database
from feme.evidence import EvidenceIngestor
from feme.export_import import ProjectExporter
from feme.integrity import IntegrityChecker
from feme.provenance import ProvenanceGraph
from feme.review import ReviewQueue
from feme.sensitive import find_sensitive, redact_text, sensitivity_score
from feme.write_governor import MemoryWriteGovernor


def test_sensitive_detection_and_redaction():
    text = "Email test@example.com and call 306-555-1212."
    findings = find_sensitive(text)
    assert {f.kind for f in findings} >= {"email", "phone"}
    assert sensitivity_score(text) > 0
    assert "test@example.com" not in redact_text(text)


def test_dedup_project_review_trace_and_integrity(tmp_path: Path):
    db = Database(str(tmp_path / "feme.sqlite"))
    db.init()
    ingestor = EvidenceIngestor(db)
    text = "Use PostgreSQL as the canonical memory database. Store raw PDFs on the external drive."
    first = ingestor.ingest_text(text, source_type="note", project_id="p1")
    second = ingestor.ingest_text(text, source_type="note", project_id="p1")
    assert first["duplicate"] is False
    assert second["duplicate"] is True

    candidates = extract_candidates_for_evidence(db, first["evidence_id"])
    governor = MemoryWriteGovernor(db)
    writes = [governor.commit_candidate(c, project_id="p1") for c in candidates]
    claim_ids = [w.matched_claim_id for w in writes if w.matched_claim_id]
    assert claim_ids

    trace = ProvenanceGraph(db).trace_claim(claim_ids[0])
    assert trace["evidence_links"]

    review_result = ReviewQueue(db).act(claim_ids[0], "verify", reviewer="test", reason="unit test")
    assert review_result["after_status"] == "active"

    report = IntegrityChecker(db).run(project_id="p1")
    assert "issue_count" in report
    assert report["project_id"] == "p1"


def test_export_import_and_backup(tmp_path: Path):
    source_db = Database(str(tmp_path / "source.sqlite"))
    source_db.init()
    ingestor = EvidenceIngestor(source_db)
    result = ingestor.ingest_text("The memory engine should link claims to exact spans.", project_id="p2")
    candidates = extract_candidates_for_evidence(source_db, result["evidence_id"])
    for candidate in candidates:
        MemoryWriteGovernor(source_db).commit_candidate(candidate, project_id="p2")

    export_path = tmp_path / "export.json"
    ProjectExporter(source_db).export_project("p2", export_path)
    assert export_path.exists()

    backup_path = tmp_path / "backup.sqlite"
    BackupManager(source_db).backup(backup_path)
    assert backup_path.exists()

    dest_db = Database(str(tmp_path / "dest.sqlite"))
    dest_db.init()
    imported = ProjectExporter(dest_db).import_project(export_path)
    assert imported["project_id"] == "p2"
    with dest_db.connect() as con:
        row = con.execute("SELECT COUNT(*) AS n FROM evidence_sources WHERE project_id = 'p2'").fetchone()
    assert row["n"] == 1
