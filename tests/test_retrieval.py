from feme.claim_extractor import extract_candidates_for_evidence
from feme.db import Database
from feme.evidence import EvidenceIngestor
from feme.retrieval import RetrievalPlanner
from feme.write_governor import MemoryWriteGovernor


def test_retrieval_finds_claim(tmp_path):
    db = Database(str(tmp_path / "memory.db"))
    db.init()
    result = EvidenceIngestor(db).ingest_text(
        "Use PostgreSQL as the canonical memory database."
    )
    gov = MemoryWriteGovernor(db)
    for c in extract_candidates_for_evidence(db, result["evidence_id"]):
        gov.commit_candidate(c)
    results = RetrievalPlanner(db).search("canonical database", top_k=5)
    assert results
    assert any("PostgreSQL" in r.text for r in results)


def test_retrieval_claim_quote_comes_from_support_spans(tmp_path):
    db = Database(str(tmp_path / "memory.db"))
    db.init()
    result = EvidenceIngestor(db).ingest_text(
        "Use PostgreSQL as the canonical memory database."
    )
    gov = MemoryWriteGovernor(db)
    for candidate in extract_candidates_for_evidence(db, result["evidence_id"]):
        gov.commit_candidate(candidate)

    with db.connect() as con:
        claim = con.execute(
            "SELECT id FROM memory_claims ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        assert claim is not None
        con.execute(
            "UPDATE claim_support_spans SET quote_text = ? WHERE claim_id = ?",
            ("SOURCE_OF_TRUTH_QUOTE", claim["id"]),
        )
        con.commit()

    results = RetrievalPlanner(db).search("canonical database", top_k=5)
    claim_results = [r for r in results if r.kind == "claim"]
    assert claim_results
    assert any(
        r.metadata.get("support_quote_text") == "SOURCE_OF_TRUTH_QUOTE"
        for r in claim_results
    )
