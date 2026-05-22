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

    def build_scaffold(self, question: str, *, project_id: str = "default", token_budget: int = 12000) -> dict:
        packet = ContextBuilder(self.db).build(question, project_id=project_id, token_budget=token_budget)
        citations = CitationManager(self.db).citations_for_context(packet, persist=True)
        claim_lines = []
        for item in packet.included:
            if item.get("kind") != "claim":
                continue
            labels = [c["citation_label"] for c in citations if c.get("claim_id") == item.get("claim_id")]
            claim_lines.append(
                {
                    "claim_id": item.get("claim_id"),
                    "text": item.get("text"),
                    "status": (item.get("metadata") or {}).get("status"),
                    "confidence": (item.get("metadata") or {}).get("confidence"),
                    "citations": labels,
                }
            )
        return {
            "question": question,
            "project_id": project_id,
            "risk_summary": packet.metadata.get("risk_summary", {}),
            "warnings": packet.warnings,
            "claims": claim_lines,
            "citations": citations,
            "drafting_instruction": "Answer only from the listed claims/citations. Mark unsupported or contradicted points explicitly.",
        }
