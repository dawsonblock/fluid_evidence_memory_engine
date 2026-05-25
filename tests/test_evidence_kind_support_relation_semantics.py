from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from feme.answer_builder import GroundedAnswerBuilder
from feme.extractors.schema import validate_extraction_payload


def _claim(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "subject": "FEME",
        "predicate": "must_use",
        "object": "PostgreSQL",
        "claim_text": "FEME must use PostgreSQL.",
        "support_char_start": 0,
        "support_char_end": 25,
        "support_quote_text": "FEME must use PostgreSQL.",
        "support_relation": "supports",
        "evidence_kind": "direct",
    }
    base.update(overrides)
    return base


def test_schema_accepts_direct_support_semantics():
    ok, reason = validate_extraction_payload(
        {"claims": [_claim()]},
        source_text="FEME must use PostgreSQL.",
    )
    assert ok is True
    assert reason == "ok"


def test_schema_accepts_inference_semantics():
    ok, reason = validate_extraction_payload(
        {
            "claims": [
                _claim(
                    claim_text="FEME likely requires PostgreSQL tuning.",
                    support_quote_text="FEME must use PostgreSQL.",
                    support_relation="inferred_from",
                    evidence_kind="inference",
                )
            ]
        },
        source_text="FEME must use PostgreSQL.",
    )
    assert ok is True
    assert reason == "ok"


def test_schema_accepts_summary_semantics():
    ok, reason = validate_extraction_payload(
        {
            "claims": [
                _claim(
                    claim_text="In summary, FEME uses PostgreSQL.",
                    support_quote_text="FEME must use PostgreSQL.",
                    support_relation="summarizes",
                    evidence_kind="summary",
                )
            ]
        },
        source_text="FEME must use PostgreSQL.",
    )
    assert ok is True
    assert reason == "ok"


def test_schema_accepts_contradiction_relation():
    ok, reason = validate_extraction_payload(
        {
            "claims": [
                _claim(
                    claim_text="This contradicts the previous SQLite-only claim.",
                    support_quote_text="FEME must use PostgreSQL.",
                    support_relation="contradicts",
                    evidence_kind="direct",
                )
            ]
        },
        source_text="FEME must use PostgreSQL.",
    )
    assert ok is True
    assert reason == "ok"


@dataclass
class _Packet:
    included: list[dict[str, Any]]
    warnings: list[str]
    metadata: dict[str, Any]


def test_answer_builder_adds_warning_for_inference_summary_contradiction_unknown(monkeypatch):
    packet = _Packet(
        included=[
            {
                "kind": "claim",
                "claim_id": "c1",
                "text": "Claim 1.",
                "metadata": {"status": "active", "source_quality": 0.95},
                "supporting_evidence": [
                    {"evidence_kind": "inference", "support_relation": "inferred_from"}
                ],
            },
            {
                "kind": "claim",
                "claim_id": "c2",
                "text": "Claim 2.",
                "metadata": {"status": "active", "source_quality": 0.95},
                "supporting_evidence": [
                    {"evidence_kind": "summary", "support_relation": "summarizes"}
                ],
            },
            {
                "kind": "claim",
                "claim_id": "c3",
                "text": "Claim 3.",
                "metadata": {"status": "active", "source_quality": 0.95},
                "supporting_evidence": [
                    {"evidence_kind": "unknown", "support_relation": "contradicts"}
                ],
            },
        ],
        warnings=[],
        metadata={"risk_summary": {"risk": "low"}},
    )

    monkeypatch.setattr(
        "feme.answer_builder.ContextBuilder.build",
        lambda self, question, project_id, token_budget, retrieval_mode, include_pending_review: packet,
    )
    monkeypatch.setattr(
        "feme.answer_builder.CitationManager.citations_for_context",
        lambda self, packet, persist: [
            {"citation_label": "[1]", "claim_id": "c1"},
            {"citation_label": "[2]", "claim_id": "c2"},
            {"citation_label": "[3]", "claim_id": "c3"},
        ],
    )

    scaffold = GroundedAnswerBuilder(db=None).build_scaffold("What should FEME use?")
    warnings = "\n".join(scaffold["warnings"]) 

    assert "inference-derived" in warnings
    assert "summary-derived" in warnings
    assert "contradictory support relations" in warnings
    assert "unknown evidence kind" in warnings
