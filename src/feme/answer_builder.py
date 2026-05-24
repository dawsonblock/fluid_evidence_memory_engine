from __future__ import annotations

import re

from .citations import CitationManager
from .context_builder import ContextBuilder
from .db import Database


class GroundedAnswerBuilder:
    """Creates a citation-ready answer scaffold.

    This does not hallucinate a finished narrative. It prepares the exact claims,
    warnings, and citation labels an LLM or UI should use when drafting an answer.
    """

    def __init__(self, db: Database):
        self.db = db

    def build_scaffold(
        self,
        question: str,
        *,
        project_id: str = "default",
        token_budget: int = 12000,
        retrieval_mode: str | None = None,
        include_pending_review: bool = True,
    ) -> dict:
        packet = ContextBuilder(self.db).build(
            question,
            project_id=project_id,
            token_budget=token_budget,
            retrieval_mode=retrieval_mode,
            include_pending_review=include_pending_review,
        )
        citations = CitationManager(self.db).citations_for_context(packet, persist=True)
        claim_lines = []
        warnings = list(packet.warnings)
        saw_pending_review = False
        saw_low_trust = False
        for item in packet.included:
            if item.get("kind") != "claim":
                continue
            labels = [
                c["citation_label"]
                for c in citations
                if c.get("claim_id") == item.get("claim_id")
            ]
            status = (item.get("metadata") or {}).get("status")
            source_quality = float(
                (item.get("metadata") or {}).get("source_quality") or 0.0
            )
            if status == "pending_review":
                saw_pending_review = True
            if source_quality < 0.60:
                saw_low_trust = True
            claim_lines.append(
                {
                    "claim_id": item.get("claim_id"),
                    "text": item.get("text"),
                    "status": status,
                    "confidence": (item.get("metadata") or {}).get("confidence"),
                    "source_quality": source_quality,
                    "citations": labels,
                }
            )
        if saw_pending_review:
            warnings.append(
                "Includes pending-review claims; verify review actions before external publication."
            )
        if saw_low_trust:
            warnings.append(
                "Includes lower-trust source claims; corroborate with higher-trust evidence."
            )
        # Check for inference/summary evidence_relation in supporting evidence
        saw_inference = False
        for item in packet.included:
            if item.get("kind") != "claim":
                continue
            for ev in item.get("supporting_evidence") or []:
                evidence_kind = ev.get("evidence_kind") or ev.get("evidence_relation")
                if evidence_kind in {"inference", "summary"}:
                    saw_inference = True
                    break
            if saw_inference:
                break
        if saw_inference:
            warnings.append(
                "Includes inference-derived claims; verify source spans before external use."
            )
        risk_summary = dict(packet.metadata.get("risk_summary", {}))
        if saw_inference and risk_summary.get("risk") == "low":
            risk_summary["risk"] = "medium"
        sentence_checks = _verify_sentence_citations(claim_lines)
        unsupported_count = sum(
            1 for check in sentence_checks if not bool(check.get("verified"))
        )
        citation_verification = {
            "ok": unsupported_count == 0,
            "checked_sentences": len(sentence_checks),
            "unsupported_sentences": unsupported_count,
        }
        if unsupported_count:
            warnings.append(
                "One or more answer sentences are missing citations; block publication until every sentence is grounded."
            )
        return {
            "question": question,
            "project_id": project_id,
            "risk_summary": risk_summary,
            "warnings": warnings,
            "claims": claim_lines,
            "citations": citations,
            "sentence_citation_checks": sentence_checks,
            "citation_verification": citation_verification,
            "drafting_instruction": "Answer only from the listed claims/citations. Mark unsupported or contradicted points explicitly.",
        }


def _verify_sentence_citations(claim_lines: list[dict]) -> list[dict]:
    checks: list[dict] = []
    for claim in claim_lines:
        claim_id = claim.get("claim_id")
        citations = list(claim.get("citations") or [])
        for sentence in _split_sentences(str(claim.get("text") or "")):
            checks.append(
                {
                    "claim_id": claim_id,
                    "sentence": sentence,
                    "citations": citations,
                    "verified": bool(citations),
                }
            )
    return checks


def _split_sentences(text: str) -> list[str]:
    parts = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text or "")]
    return [s for s in parts if s]
