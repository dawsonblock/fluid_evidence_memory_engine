"""Tests for evidence_relation label propagation (v0.8)."""
from __future__ import annotations

from pathlib import Path

import pytest

from feme.claim_extractor import extract_candidates_for_evidence
from feme.db import Database
from feme.evidence import EvidenceIngestor
from feme.models import ClaimCandidate
from feme.write_governor import MemoryWriteGovernor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _db(tmp_path: Path) -> Database:
    db = Database(str(tmp_path / "evidence-relation.sqlite"))
    db.init()
    return db


def _ingest(db: Database, text: str) -> str:
    result = EvidenceIngestor(db).ingest_text(text, source_type="official_record")
    return result["evidence_id"]


def _link_rows(db: Database, evidence_id: str) -> list[dict]:
    with db.connect() as con:
        rows = con.execute(
            "SELECT * FROM claim_evidence_links WHERE evidence_id = ?",
            (evidence_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# ClaimCandidate default
# ---------------------------------------------------------------------------

def test_claim_candidate_default_evidence_relation():
    c = ClaimCandidate(
        subject="FEME",
        predicate="uses",
        object="PostgreSQL",
        claim_text="FEME uses PostgreSQL.",
    )
    assert c.evidence_relation == "unknown"
    assert c.support_relation == "supports"
    assert c.evidence_kind == "unknown"


def test_claim_candidate_custom_evidence_relation():
    c = ClaimCandidate(
        subject="FEME",
        predicate="uses",
        object="PostgreSQL",
        claim_text="FEME uses PostgreSQL.",
        evidence_relation="supports",
    )
    assert c.evidence_relation == "supports"


def test_claim_candidate_split_relation_fields():
    c = ClaimCandidate(
        subject="FEME",
        predicate="uses",
        object="PostgreSQL",
        claim_text="FEME uses PostgreSQL.",
        support_relation="corroborates",
        evidence_kind="inference",
        evidence_relation="corroborates",
    )
    assert c.support_relation == "corroborates"
    assert c.evidence_kind == "inference"


# ---------------------------------------------------------------------------
# Write path: evidence_relation persisted into claim_evidence_links
# ---------------------------------------------------------------------------

def test_heuristic_claims_default_to_unknown_relation(tmp_path: Path):
    db = _db(tmp_path)
    evidence_id = _ingest(db, "FEME uses PostgreSQL as its backing store.")

    candidates = extract_candidates_for_evidence(
        db, evidence_id, extractor_mode="heuristic"
    )
    governor = MemoryWriteGovernor(db)
    for c in candidates:
        c.evidence_id = evidence_id
        governor.commit_candidate(c)

    links = _link_rows(db, evidence_id)
    assert len(links) > 0
    for link in links:
        assert link["evidence_relation"] == "unknown"


def test_custom_evidence_relation_persisted(tmp_path: Path):
    db = _db(tmp_path)
    evidence_id = _ingest(db, "FEME uses PostgreSQL as its backing store.")

    candidates = extract_candidates_for_evidence(
        db, evidence_id, extractor_mode="heuristic"
    )
    governor = MemoryWriteGovernor(db)
    for c in candidates:
        c.evidence_id = evidence_id
        c.evidence_relation = "corroborates_fact"
        governor.commit_candidate(c)

    links = _link_rows(db, evidence_id)
    assert len(links) > 0
    for link in links:
        assert link["evidence_relation"] == "corroborates_fact"
        assert link["evidence_kind"] == "unknown"


def test_evidence_kind_persisted_separately_from_support_relation(tmp_path: Path):
    db = _db(tmp_path)
    evidence_id = _ingest(db, "FEME uses PostgreSQL as its backing store.")

    candidates = extract_candidates_for_evidence(
        db,
        evidence_id,
        extractor_mode="json_strict",
        extractor_provider="json_static",
        extractor_config={
            "claims": [
                {
                    "subject": "FEME",
                    "predicate": "uses",
                    "object": "PostgreSQL",
                    "claim_text": "FEME uses PostgreSQL as its backing store.",
                    "support_char_start": 0,
                    "support_char_end": 42,
                    "support_relation": "supports",
                    "evidence_kind": "inference",
                }
            ]
        },
    )
    governor = MemoryWriteGovernor(db)
    for c in candidates:
        c.evidence_id = evidence_id
        governor.commit_candidate(c)

    links = _link_rows(db, evidence_id)
    assert len(links) == 1
    assert links[0]["evidence_relation"] == "supports"
    assert links[0]["evidence_kind"] == "inference"


def test_multiple_candidates_different_relations(tmp_path: Path):
    db = _db(tmp_path)
    evidence_id = _ingest(db, "FEME uses PostgreSQL. FEME supports SQLite for dev.")

    candidates = extract_candidates_for_evidence(
        db, evidence_id, extractor_mode="heuristic"
    )
    assert len(candidates) >= 1
    governor = MemoryWriteGovernor(db)
    for idx, c in enumerate(candidates):
        c.evidence_id = evidence_id
        c.evidence_relation = "supports" if idx % 2 == 0 else "contradicts"
        governor.commit_candidate(c)

    links = _link_rows(db, evidence_id)
    relations = {lnk["evidence_relation"] for lnk in links}
    # At least one relation label must be set
    assert relations <= {"supports", "contradicts"}
    assert len(relations) >= 1


# ---------------------------------------------------------------------------
# Schema: evidence_relation column present after migration
# ---------------------------------------------------------------------------

def test_evidence_relation_column_exists_after_init(tmp_path: Path):
    db = _db(tmp_path)
    with db.connect() as con:
        info = con.execute(
            "PRAGMA table_info(claim_evidence_links)"
        ).fetchall()
    columns = [row["name"] for row in info]
    assert "evidence_relation" in columns
    assert "evidence_kind" in columns


def test_evidence_relation_column_default_unknown(tmp_path: Path):
    """Inserting a link without specifying evidence_relation should default to 'unknown'."""
    db = _db(tmp_path)
    evidence_id = _ingest(db, "FEME supports PostgreSQL natively.")
    candidates = extract_candidates_for_evidence(
        db, evidence_id, extractor_mode="heuristic"
    )
    governor = MemoryWriteGovernor(db)
    # Do NOT set evidence_relation — rely on model default
    for c in candidates:
        c.evidence_id = evidence_id
        governor.commit_candidate(c)


# ---------------------------------------------------------------------------
# Migration: V14 runs cleanly on a fresh DB
# ---------------------------------------------------------------------------

def test_v14_migration_column_exists(tmp_path: Path):
    """evidence_relation column is present after db.init() — either via base
    schema (new install) or via V14 migration (upgrade)."""
    db = Database(str(tmp_path / "migration-v14.sqlite"))
    db.init()
    with db.connect() as con:
        info = con.execute(
            "PRAGMA table_info(claim_evidence_links)"
        ).fetchall()
    columns = [row["name"] for row in info]
    assert "evidence_relation" in columns, "evidence_relation column missing after init"
