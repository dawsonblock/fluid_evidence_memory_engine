from __future__ import annotations

from .db import Database
from .models import ContextPacket, VerificationReport


class AnswerVerifier:
    """Grounding verifier for context packets and draft answers.

    This does not prove an answer true. It checks whether the selected context is
    evidence-linked, whether disputed claims are present, and whether the draft
    appears to introduce factual nouns not present in the packet.
    """

    def __init__(self, db: Database):
        self.db = db

    def verify_context(self, packet: ContextPacket) -> VerificationReport:
        issues: list[dict] = []
        checked_claim_ids: list[str] = []
        checked_span_ids: list[str] = []
        for item in packet.included:
            if item.get("kind") == "claim":
                claim_id = item.get("claim_id")
                if claim_id:
                    checked_claim_ids.append(claim_id)
                status = (item.get("metadata") or {}).get("status")
                if status in {"disputed", "superseded", "rejected", "archived", "stale"}:
                    issues.append({"severity": "high", "type": "unsafe_claim_status", "claim_id": claim_id, "status": status})
                support = item.get("supporting_evidence") or []
                if not support:
                    issues.append({"severity": "medium", "type": "claim_without_supporting_evidence", "claim_id": claim_id})
                for s in support:
                    if s.get("span_id"):
                        checked_span_ids.append(s["span_id"])
            elif item.get("kind") == "chunk":
                checked_span_ids.extend(item.get("span_ids") or [])
                if not item.get("evidence_id"):
                    issues.append({"severity": "medium", "type": "chunk_without_evidence_id", "id": item.get("id")})
        risk = "low"
        if any(i["severity"] == "high" for i in issues):
            risk = "high"
        elif issues:
            risk = "medium"
        return VerificationReport(
            ok=not issues,
            risk_level=risk,
            issue_count=len(issues),
            issues=issues,
            checked_claim_ids=checked_claim_ids,
            checked_span_ids=checked_span_ids,
            warnings=packet.warnings,
        )

    def verify_answer_text(self, packet: ContextPacket, answer_text: str) -> VerificationReport:
        report = self.verify_context(packet)
        context_text = "\n".join(str(i.get("text", "")) for i in packet.included).lower()
        answer_terms = {w.lower() for w in answer_text.split() if len(w) > 5}
        unsupported = sorted(w for w in answer_terms if w not in context_text)[:15]
        if unsupported:
            report.issues.append({"severity": "low", "type": "draft_contains_terms_not_seen_in_context", "terms": unsupported})
            report.issue_count = len(report.issues)
            if report.risk_level == "low":
                report.risk_level = "medium"
            report.ok = False
        return report
