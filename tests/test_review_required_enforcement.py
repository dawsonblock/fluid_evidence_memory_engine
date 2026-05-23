from pathlib import Path

import importlib

import pytest
from feme.answer_builder import GroundedAnswerBuilder
from feme.claim_extractor import extract_candidates_for_evidence
from feme.db import Database
from feme.evidence import EvidenceIngestor
from feme.review import ReviewQueue
from feme.retrieval import RetrievalPlanner
from feme.source_registry import SourceRegistry
from feme.write_governor import MemoryWriteGovernor


def _db(tmp_path: Path) -> Database:
    db = Database(str(tmp_path / "feme.sqlite"))
    db.init()
    return db


def _ingest_review_required_claim(db: Database, *, project_id: str = "default") -> str:
    SourceRegistry(db).upsert(
        "human_note",
        project_id=project_id,
        enabled=True,
        default_quality=0.9,
        review_required=True,
    )
    evidence = EvidenceIngestor(db).ingest_text(
        "The memory engine must use PostgreSQL as canonical database.",
        source_type="human_note",
        project_id=project_id,
    )
    candidates = extract_candidates_for_evidence(db, evidence["evidence_id"])
    writes = [
        MemoryWriteGovernor(db).commit_candidate(c, project_id=project_id)
        for c in candidates
    ]
    claim_ids = [w.matched_claim_id for w in writes if w.matched_claim_id]
    assert claim_ids
    return claim_ids[0]


def _ingest_review_required_evidence(
    db: Database, *, project_id: str = "default"
) -> str:
    SourceRegistry(db).upsert(
        "human_note",
        project_id=project_id,
        enabled=True,
        default_quality=0.9,
        review_required=True,
    )
    evidence = EvidenceIngestor(db).ingest_text(
        "The memory engine must use PostgreSQL as canonical database.",
        source_type="human_note",
        project_id=project_id,
    )
    candidates = extract_candidates_for_evidence(db, evidence["evidence_id"])
    assert candidates
    writes = [
        MemoryWriteGovernor(db).commit_candidate(c, project_id=project_id)
        for c in candidates
    ]
    assert any(w.matched_claim_id for w in writes)
    return evidence["evidence_id"]


def test_review_required_source_forces_pending_review(tmp_path: Path):
    db = _db(tmp_path)
    claim_id = _ingest_review_required_claim(db, project_id="p-review")

    with db.connect() as con:
        row = con.execute(
            "SELECT status FROM memory_claims WHERE id = ?",
            (claim_id,),
        ).fetchone()
    assert row["status"] == "pending_review"

    pending = ReviewQueue(db).list_pending(project_id="p-review")
    assert any(item["id"] == claim_id for item in pending)


def test_search_can_exclude_pending_review_claims(tmp_path: Path):
    db = _db(tmp_path)
    claim_id = _ingest_review_required_claim(db, project_id="p-search")

    without_pending = RetrievalPlanner(db).search(
        "canonical database",
        project_id="p-search",
        include_pending_review=False,
    )
    assert all(r.claim_id != claim_id for r in without_pending)

    with_pending = RetrievalPlanner(db).search(
        "canonical database",
        project_id="p-search",
        include_pending_review=True,
    )
    assert any(r.claim_id == claim_id for r in with_pending)


def test_search_excludes_pending_review_chunks(tmp_path: Path):
    db = _db(tmp_path)
    evidence_id = _ingest_review_required_evidence(db, project_id="p-search-chunks")

    without_pending = RetrievalPlanner(db).search(
        "canonical database",
        project_id="p-search-chunks",
        include_pending_review=False,
    )
    assert all(
        not (r.kind == "chunk" and r.evidence_id == evidence_id)
        for r in without_pending
    )

    with_pending = RetrievalPlanner(db).search(
        "canonical database",
        project_id="p-search-chunks",
        include_pending_review=True,
    )
    assert any(r.kind == "chunk" and r.evidence_id == evidence_id for r in with_pending)


def test_public_retrieval_mode_is_strict(tmp_path: Path):
    db = _db(tmp_path)
    claim_id = _ingest_review_required_claim(db, project_id="p-public-mode")
    evidence_id = _ingest_review_required_evidence(db, project_id="p-public-mode")

    strict_public = RetrievalPlanner(db).search(
        "canonical database",
        project_id="p-public-mode",
        retrieval_mode="public",
        include_pending_review=True,
    )
    assert all(r.claim_id != claim_id for r in strict_public)
    assert all(
        not (r.kind == "chunk" and r.evidence_id == evidence_id) for r in strict_public
    )

    internal = RetrievalPlanner(db).search(
        "canonical database",
        project_id="p-public-mode",
        retrieval_mode="internal",
        include_pending_review=True,
    )
    assert any(r.claim_id == claim_id for r in internal)
    assert any(r.kind == "chunk" and r.evidence_id == evidence_id for r in internal)


def test_answer_scaffold_warns_on_pending_review(tmp_path: Path):
    db = _db(tmp_path)
    _ingest_review_required_claim(db, project_id="p-answer")

    scaffold = GroundedAnswerBuilder(db).build_scaffold(
        "What database should we use?",
        project_id="p-answer",
        include_pending_review=True,
    )
    warning_text = "\n".join(scaffold["warnings"]).lower()
    assert "pending" in warning_text
    assert "review" in warning_text


def test_pending_review_creation_writes_review_action(tmp_path: Path):
    db = _db(tmp_path)
    claim_id = _ingest_review_required_claim(db, project_id="p-review-action")

    with db.connect() as con:
        row = con.execute(
            """
            SELECT action, reviewer, before_status, after_status, reason
            FROM review_actions
            WHERE claim_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (claim_id,),
        ).fetchone()
    assert row
    assert row["action"] == "pending_created"
    assert row["reviewer"] == "system"
    assert row["before_status"] is None
    assert row["after_status"] == "pending_review"
    assert "review_required" in row["reason"]


def test_review_evidence_updates_status_and_audits(tmp_path: Path):
    db = _db(tmp_path)
    evidence = EvidenceIngestor(db).ingest_text(
        "Disk snapshots are retained weekly.",
        source_type="note",
        project_id="p-evidence",
    )

    result = ReviewQueue(db).review_evidence(
        evidence["evidence_id"],
        "approve",
        reviewer="qa",
        reason="validated source",
    )
    assert result["after_status"] == "active"

    with db.connect() as con:
        row = con.execute(
            "SELECT review_status FROM evidence_sources WHERE id = ?",
            (evidence["evidence_id"],),
        ).fetchone()
        audit = con.execute(
            "SELECT action FROM review_actions WHERE metadata_json LIKE ? ORDER BY created_at DESC LIMIT 1",
            (f'%"evidence_id": "{evidence["evidence_id"]}"%',),
        ).fetchone()
    assert row["review_status"] == "active"
    assert audit["action"] == "evidence_approve"


def test_api_and_cli_honor_pending_review_filter(tmp_path: Path, capsys, monkeypatch):
    db = _db(tmp_path)
    claim_id = _ingest_review_required_claim(db, project_id="p-filter")
    evidence_id = _ingest_review_required_evidence(db, project_id="p-filter")

    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    monkeypatch.setenv("FEME_DB_BACKEND", "sqlite")
    monkeypatch.setenv("FEME_DB_PATH", str(tmp_path / "api.sqlite"))
    monkeypatch.delenv("FEME_POSTGRES_DSN", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    config = importlib.import_module("feme.config")
    importlib.reload(config)
    api = importlib.import_module("feme.api")
    original_db = api.database
    api.database = db
    try:
        client = fastapi_testclient.TestClient(api.app)

        search = client.post(
            "/search",
            json={
                "query": "canonical database",
                "project_id": "p-filter",
                "include_pending_review": False,
            },
        )
        assert search.status_code == 200
        search_payload = search.json()
        assert all(item["claim_id"] != claim_id for item in search_payload)
        assert all(
            not (item.get("kind") == "chunk" and item.get("evidence_id") == evidence_id)
            for item in search_payload
        )

        search_with_pending = client.post(
            "/search",
            json={
                "query": "canonical database",
                "project_id": "p-filter",
                "include_pending_review": True,
            },
        )
        assert search_with_pending.status_code == 200
        assert any(item["claim_id"] == claim_id for item in search_with_pending.json())

        public_with_pending = client.post(
            "/search",
            json={
                "query": "canonical database",
                "project_id": "p-filter",
                "retrieval_mode": "public",
                "include_pending_review": True,
            },
        )
        assert public_with_pending.status_code == 200
        public_payload = public_with_pending.json()
        assert all(item["claim_id"] != claim_id for item in public_payload)
        assert all(
            not (item.get("kind") == "chunk" and item.get("evidence_id") == evidence_id)
            for item in public_payload
        )

        context = client.post(
            "/context",
            json={
                "question": "What database should we use?",
                "project_id": "p-filter",
                "include_pending_review": True,
            },
        )
        assert context.status_code == 200
        assert any(
            "pending review" in warning.lower()
            for warning in context.json()["warnings"]
        )

        review = client.post(
            "/review/evidence",
            json={
                "evidence_id": evidence_id,
                "action": "approve",
                "reviewer": "tester",
            },
        )
        assert review.status_code == 200
        assert review.json()["after_status"] == "active"
    finally:
        api.database = original_db

    cli = importlib.import_module("feme.cli")
    cli.search(
        db=str(db.path),
        query="canonical database",
        project_id="p-filter",
        include_pending_review=False,
    )
    captured = capsys.readouterr().out
    assert "pending_review" not in captured

    cli.search(
        db=str(db.path),
        query="canonical database",
        project_id="p-filter",
        include_pending_review=True,
    )
    captured = capsys.readouterr().out
    assert claim_id in captured

    cli.search(
        db=str(db.path),
        query="canonical database",
        project_id="p-filter",
        retrieval_mode="public",
        include_pending_review=True,
    )
    captured = capsys.readouterr().out
    assert claim_id not in captured

    cli.context(
        db=str(db.path),
        question="What database should we use?",
        project_id="p-filter",
        budget=12000,
        include_pending_review=True,
    )
    captured = capsys.readouterr().out
    assert "pending_review" in captured
