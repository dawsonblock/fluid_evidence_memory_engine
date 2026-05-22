from feme.db import Database
from feme.models import ClaimCandidate, MemoryType
from feme.write_governor import MemoryWriteGovernor


def test_governor_saves_project_decision(tmp_path):
    db = Database(str(tmp_path / "memory.db"))
    db.init()
    candidate = ClaimCandidate(
        subject="memory engine",
        predicate="uses_database",
        object="PostgreSQL",
        claim_text="Use PostgreSQL as the canonical memory database.",
        memory_type=MemoryType.project_decision,
        user_explicitness=1.0,
        long_term_usefulness=0.95,
        project_relevance=0.95,
        source_quality=0.6,
        uncertainty=0.05,
        triviality=0.0,
        short_livedness=0.0,
    )
    result = MemoryWriteGovernor(db).commit_candidate(candidate)
    assert result.decision.value in {"save_new", "merge_with_existing"}
    with db.connect() as con:
        count = con.execute("SELECT COUNT(*) AS n FROM memory_claims").fetchone()["n"]
    assert count == 1
