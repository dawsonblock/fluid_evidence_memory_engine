from __future__ import annotations

import hashlib
from pathlib import Path

from feme.claim_extractor import extract_candidates_for_evidence
from feme.db import Database
from feme.evidence import EvidenceIngestor
from feme.write_governor import MemoryWriteGovernor


def _db(tmp_path: Path) -> Database:
    db = Database(str(tmp_path / "support-spans.sqlite"))
    db.init()
    return db


def test_heuristic_support_quote_matches_source_slice(tmp_path: Path):
    db = _db(tmp_path)
    text = "  FEME must use PostgreSQL as canonical memory.  "
    evidence_id = EvidenceIngestor(db).ingest_text(text, source_type="official_record")[
        "evidence_id"
    ]

    candidates = extract_candidates_for_evidence(db, evidence_id, extractor_mode="heuristic")
    assert candidates

    c0 = candidates[0]
    assert c0.support_char_start is not None
    assert c0.support_char_end is not None
    quote = text[c0.support_char_start : c0.support_char_end]
    assert c0.support_quote_text == quote


def test_support_span_quote_sha256_uses_exact_quote_text(tmp_path: Path):
    db = _db(tmp_path)
    text = "FEME must use PostgreSQL as canonical memory."
    evidence_id = EvidenceIngestor(db).ingest_text(text, source_type="official_record")[
        "evidence_id"
    ]
    candidates = extract_candidates_for_evidence(db, evidence_id, extractor_mode="heuristic")
    assert candidates

    governor = MemoryWriteGovernor(db)
    decision = governor.commit_candidate(candidates[0])
    assert decision.decision.value in {
        "save_new",
        "save_as_inference_only",
        "needs_human_review",
    }

    with db.connect() as con:
        row = con.execute(
            "SELECT quote_text, quote_sha256 FROM claim_support_spans ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    assert row is not None
    expected_hash = hashlib.sha256(row["quote_text"].encode("utf-8")).hexdigest()
    assert row["quote_sha256"] == expected_hash
