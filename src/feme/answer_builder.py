from __future__ import annotations

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
        include_pending_review: bool = True,
    ) -> dict:
        packet = ContextBuilder(self.db).build(
            question,
            project_id=project_id,
            token_budget=token_budget,
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
        return {
            "question": question,
            "project_id": project_id,
            "risk_summary": packet.metadata.get("risk_summary", {}),
            "warnings": warnings,
            "claims": claim_lines,
            "citations": citations,
            "drafting_instruction": "Answer only from the listed claims/citations. Mark unsupported or contradicted points explicitly.",
        }
