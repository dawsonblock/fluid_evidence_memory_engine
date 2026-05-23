from pathlib import Path

from feme.claim_extractor import extract_candidates_for_evidence
from feme.context_builder import ContextBuilder
from feme.citations import CitationManager
from feme.db import Database
from feme.evidence import EvidenceIngestor
from feme.export_import import ProjectExporter
from feme.lifecycle import MemoryLifecycleManager
from feme.models import ClaimCandidate, MemoryType
from feme.retrieval import RetrievalPlanner
from feme.verifier import AnswerVerifier
from feme.write_governor import MemoryWriteGovernor


def make_db(tmp_path: Path) -> Database:
    db = Database(str(tmp_path / "test.sqlite"))
    db.init()
    return db


def test_claims_are_linked_to_exact_token_spans(tmp_path):
    db = make_db(tmp_path)
    result = EvidenceIngestor(db).ingest_text(
        "Use PostgreSQL as the canonical memory database.",
        source_type="note",
        project_id="memory",
    )
    candidates = extract_candidates_for_evidence(db, result["evidence_id"])
    assert candidates
    assert candidates[0].span_id in result["span_ids"]
    write = MemoryWriteGovernor(db).commit_candidate(candidates[0], project_id="memory")
    assert write.matched_claim_id
    with db.connect() as con:
        row = con.execute(
            "SELECT span_id FROM claim_evidence_links WHERE claim_id = ?",
            (write.matched_claim_id,),
        ).fetchone()
    assert row["span_id"] in result["span_ids"]


def test_support_spans_are_exposed_with_exact_offsets(tmp_path):
    db = make_db(tmp_path)
    text = "Background context should be ignored. Use PostgreSQL as the canonical memory database."
    expected_sentence = "Use PostgreSQL as the canonical memory database."
    result = EvidenceIngestor(db).ingest_text(
        text,
        source_type="note",
        project_id="memory",
    )
    candidates = extract_candidates_for_evidence(db, result["evidence_id"])
    write = MemoryWriteGovernor(db).commit_candidate(candidates[0], project_id="memory")

    packet = ContextBuilder(db).build(
        "canonical memory database",
        project_id="memory",
        include_pending_review=True,
    )
    claim_items = [item for item in packet.included if item.get("kind") == "claim"]
    assert claim_items
    evidence = claim_items[0]["supporting_evidence"][0]
    assert evidence["char_start"] < evidence["char_end"]
    assert evidence["token_start"] is not None
    assert evidence["token_end"] is not None
    assert evidence["token_start"] < evidence["token_end"]
    assert evidence["quote_text"] == expected_sentence
    assert evidence["quote_text"] == text[evidence["char_start"] : evidence["char_end"]]

    with db.connect() as con:
        support_row = con.execute(
            "SELECT quote_text, token_start, token_end FROM claim_support_spans WHERE claim_id = ?",
            (write.matched_claim_id,),
        ).fetchone()
    assert support_row
    assert support_row["quote_text"] == expected_sentence
    assert support_row["token_start"] is not None
    assert support_row["token_end"] is not None
    assert support_row["token_start"] < support_row["token_end"]

    citations = CitationManager(db).citations_for_context(packet)
    assert citations
    assert citations[0]["quote_text"] == evidence["quote_text"]
    assert citations[0]["token_start"] is not None
    assert citations[0]["token_end"] is not None


def test_chunk_retrieval_is_project_scoped(tmp_path):
    db = make_db(tmp_path)
    EvidenceIngestor(db).ingest_text(
        "Alpha project uses Postgres memory.", project_id="alpha"
    )
    EvidenceIngestor(db).ingest_text(
        "Beta project uses Qdrant memory.", project_id="beta"
    )
    results = RetrievalPlanner(db).search("Qdrant", project_id="alpha", top_k=5)
    assert all("Beta project" not in r.text for r in results)


def test_context_verifier_flags_unsupported_claim(tmp_path):
    db = make_db(tmp_path)
    candidate = ClaimCandidate(
        subject="system",
        predicate="uses",
        object="unsupported memory",
        claim_text="The system uses unsupported memory.",
        memory_type=MemoryType.project_decision,
        project_relevance=1.0,
        user_explicitness=1.0,
    )
    MemoryWriteGovernor(db).commit_candidate(candidate, project_id="memory")
    packet = ContextBuilder(db).build("unsupported memory", project_id="memory")
    report = AnswerVerifier(db).verify_context(packet)
    assert not report.ok
    assert any(i["type"] == "claim_without_supporting_evidence" for i in report.issues)


def test_lifecycle_decay_and_export(tmp_path):
    db = make_db(tmp_path)
    candidate = ClaimCandidate(
        subject="memory system",
        predicate="uses",
        object="PostgreSQL",
        claim_text="Memory system uses PostgreSQL.",
        memory_type=MemoryType.project_decision,
        project_relevance=1.0,
        user_explicitness=1.0,
        salience=0.2,
    )
    MemoryWriteGovernor(db).commit_candidate(candidate, project_id="memory")
    decay = MemoryLifecycleManager(db).run_decay(project_id="memory")
    assert decay["changed"] >= 1
    export_path = tmp_path / "export.json"
    result = ProjectExporter(db).export_project("memory", export_path)
    assert export_path.exists()
    assert result["project_id"] == "memory"
