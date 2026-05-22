from feme.db import Database
from feme.evidence import EvidenceIngestor
from feme.claim_extractor import extract_candidates_for_evidence
from feme.write_governor import MemoryWriteGovernor
from feme.retrieval import RetrievalPlanner


def test_retrieval_finds_claim(tmp_path):
    db = Database(str(tmp_path / "memory.db"))
    db.init()
    result = EvidenceIngestor(db).ingest_text("Use PostgreSQL as the canonical memory database.")
    gov = MemoryWriteGovernor(db)
    for c in extract_candidates_for_evidence(db, result["evidence_id"]):
        gov.commit_candidate(c)
    results = RetrievalPlanner(db).search("canonical database", top_k=5)
    assert results
    assert any("PostgreSQL" in r.text for r in results)
