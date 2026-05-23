from concurrent.futures import ThreadPoolExecutor

import pytest

from feme.db import Database
from feme.evidence import EvidenceIngestor


def test_ingest_creates_chunks(tmp_path):
    db = Database(str(tmp_path / "memory.db"))
    db.init()
    result = EvidenceIngestor(db).ingest_text(
        "Use PostgreSQL as canonical memory. Claims link to evidence spans."
    )
    assert result["evidence_id"].startswith("ev_")
    assert result["chunk_ids"]
    with db.connect() as con:
        count = con.execute("SELECT COUNT(*) AS n FROM text_chunks").fetchone()["n"]
    assert count >= 1


def test_ingest_duplicate_same_text_returns_existing_evidence(tmp_path):
    db = Database(str(tmp_path / "memory.db"))
    db.init()
    ingestor = EvidenceIngestor(db)
    text = "Use PostgreSQL as canonical memory. Claims link to evidence spans."

    first = ingestor.ingest_text(text, deduplicate=False)
    second = ingestor.ingest_text(text, deduplicate=False)

    assert first["duplicate"] is False
    assert second["duplicate"] is True
    assert second["evidence_id"] == first["evidence_id"]
    with db.connect() as con:
        rows = con.execute(
            "SELECT COUNT(*) AS n FROM evidence_sources WHERE project_id = ? AND sha256 = ?",
            (
                "default",
                con.execute(
                    "SELECT sha256 FROM evidence_sources WHERE id = ?",
                    (first["evidence_id"],),
                ).fetchone()["sha256"],
            ),
        ).fetchone()
    assert int(rows["n"]) == 1


def test_ingest_duplicate_parallel_writers_resolve_to_single_evidence(tmp_path):
    db = Database(str(tmp_path / "memory.db"))
    db.init()
    text = "Parallel writers should resolve duplicate evidence to one canonical row."

    def _ingest_once(_i: int) -> dict:
        return EvidenceIngestor(db).ingest_text(text, deduplicate=False)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(_ingest_once, range(20)))

    evidence_ids = {r["evidence_id"] for r in results}
    assert len(evidence_ids) == 1
    assert any(r["duplicate"] is False for r in results)
    assert any(r["duplicate"] is True for r in results)

    canonical_id = next(iter(evidence_ids))
    with db.connect() as con:
        sha = con.execute(
            "SELECT sha256 FROM evidence_sources WHERE id = ?",
            (canonical_id,),
        ).fetchone()["sha256"]
        n = con.execute(
            "SELECT COUNT(*) AS n FROM evidence_sources WHERE project_id = ? AND sha256 = ?",
            ("default", sha),
        ).fetchone()["n"]
    assert int(n) == 1


def test_ingest_rolls_back_when_timeline_build_fails(tmp_path, monkeypatch):
    db = Database(str(tmp_path / "memory.db"))
    db.init()

    def _boom(*args, **kwargs):
        raise RuntimeError("timeline failure")

    monkeypatch.setattr(
        "feme.temporal.TimelineManager.build_for_evidence",
        _boom,
    )

    with pytest.raises(RuntimeError, match="timeline failure"):
        EvidenceIngestor(db).ingest_text(
            "Use PostgreSQL as canonical memory. Claims link to evidence spans.",
        )

    with db.connect() as con:
        evidence_count = con.execute(
            "SELECT COUNT(*) AS n FROM evidence_sources"
        ).fetchone()["n"]
        chunk_count = con.execute("SELECT COUNT(*) AS n FROM text_chunks").fetchone()[
            "n"
        ]
        mention_count = con.execute(
            "SELECT COUNT(*) AS n FROM entity_mentions"
        ).fetchone()["n"]
    assert int(evidence_count) == 0
    assert int(chunk_count) == 0
    assert int(mention_count) == 0
