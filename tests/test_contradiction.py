from feme.contradiction import ContradictionEngine
from feme.db import Database
from feme.models import ClaimCandidate, MemoryType
from feme.write_governor import MemoryWriteGovernor


def test_contradiction_marks_disputed(tmp_path):
    db = Database(str(tmp_path / "memory.db"))
    db.init()
    gov = MemoryWriteGovernor(db)
    a = ClaimCandidate(
        subject="feature_x",
        predicate="is",
        object="enabled",
        claim_text="feature_x is enabled.",
        memory_type=MemoryType.project_decision,
        user_explicitness=1.0,
        project_relevance=1.0,
        long_term_usefulness=1.0,
        uncertainty=0.05,
        triviality=0.0,
        short_livedness=0.0,
    )
    b = ClaimCandidate(
        subject="feature_x",
        predicate="is",
        object="disabled",
        claim_text="feature_x is not enabled.",
        memory_type=MemoryType.project_decision,
        user_explicitness=1.0,
        project_relevance=1.0,
        long_term_usefulness=1.0,
        uncertainty=0.05,
        triviality=0.0,
        short_livedness=0.0,
    )
    gov.commit_candidate(a)
    rb = gov.commit_candidate(b)
    engine = ContradictionEngine(db)
    engine.scan_new_claim(rb.matched_claim_id)
    with db.connect() as con:
        count = con.execute(
            "SELECT COUNT(*) AS n FROM memory_contradictions"
        ).fetchone()["n"]
    assert count >= 1
