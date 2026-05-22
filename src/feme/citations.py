from __future__ import annotations

from .db import Database, rows_to_dicts
from .models import ContextPacket
from .utils import json_dumps, new_id, now_iso


class CitationManager:
    def __init__(self, db: Database):
        self.db = db

    def citations_for_context(self, packet: ContextPacket, *, persist: bool = False) -> list[dict]:
        citations: list[dict] = []
        seen: set[tuple[str, str | None, int | None, int | None]] = set()
        for item in packet.included:
            if item.get("kind") == "claim":
                for ev in item.get("supporting_evidence") or []:
                    key = (ev["evidence_id"], ev.get("span_id"), ev.get("char_start"), ev.get("char_end"))
                    if key in seen:
                        continue
                    seen.add(key)
                    citations.append(self._citation_from_link(ev, claim_id=item.get("claim_id"), text=item.get("text")))
            elif item.get("kind") == "chunk":
                source = item.get("source") or {}
                span_ids = item.get("span_ids") or []
                if span_ids:
                    spans = self._spans(span_ids)
                    for span in spans:
                        key = (span["evidence_id"], span["id"], span["char_start"], span["char_end"])
                        if key in seen:
                            continue
                        seen.add(key)
                        citations.append(self._citation_from_span(span, source=source))
        citations = [{**c, "citation_label": f"C{i + 1}"} for i, c in enumerate(citations)]
        if persist:
            self.persist_citations(packet.question, citations, project_id=str(packet.metadata.get("project_id", "default")))
        return citations

    def persist_citations(self, question: str, citations: list[dict], *, project_id: str = "default") -> dict:
        now = now_iso()
        citation_set_id = new_id("cite_set")
        with self.db.connect() as con:
            for cit in citations:
                con.execute(
                    """
                    INSERT INTO citation_records
                    (id, project_id, citation_set_id, question, citation_label, evidence_id, claim_id, span_id, quote_text, source_title, source_uri, char_start, char_end, created_at, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        new_id("cite"),
                        project_id,
                        citation_set_id,
                        question,
                        cit.get("citation_label"),
                        cit.get("evidence_id"),
                        cit.get("claim_id"),
                        cit.get("span_id"),
                        cit.get("quote_text"),
                        cit.get("source_title"),
                        cit.get("source_uri"),
                        cit.get("char_start"),
                        cit.get("char_end"),
                        now,
                        json_dumps(cit.get("metadata", {})),
                    ),
                )
            con.commit()
        return {"citation_set_id": citation_set_id, "count": len(citations)}

    def list_records(self, *, citation_set_id: str | None = None, limit: int = 100) -> list[dict]:
        with self.db.connect() as con:
            if citation_set_id:
                rows = con.execute("SELECT * FROM citation_records WHERE citation_set_id = ? ORDER BY citation_label LIMIT ?", (citation_set_id, limit)).fetchall()
            else:
                rows = con.execute("SELECT * FROM citation_records ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return rows_to_dicts(rows)

    def _citation_from_link(self, link: dict, *, claim_id: str | None, text: str | None) -> dict:
        quote = link.get("span_text") or text or ""
        return {
            "evidence_id": link.get("evidence_id"),
            "claim_id": claim_id,
            "span_id": link.get("span_id"),
            "source_title": link.get("title"),
            "source_type": link.get("source_type"),
            "source_uri": link.get("source_uri"),
            "source_sha256": link.get("sha256"),
            "char_start": link.get("char_start"),
            "char_end": link.get("char_end"),
            "token_start": link.get("token_start"),
            "token_end": link.get("token_end"),
            "quote_text": _short_quote(quote),
            "metadata": {"support_type": link.get("support_type"), "link_confidence": link.get("confidence")},
        }

    def _citation_from_span(self, span: dict, *, source: dict) -> dict:
        return {
            "evidence_id": span.get("evidence_id"),
            "claim_id": None,
            "span_id": span.get("id"),
            "source_title": source.get("title"),
            "source_type": source.get("source_type"),
            "source_uri": source.get("source_uri"),
            "source_sha256": source.get("sha256"),
            "char_start": span.get("char_start"),
            "char_end": span.get("char_end"),
            "token_start": span.get("token_start"),
            "token_end": span.get("token_end"),
            "quote_text": _short_quote(span.get("text") or ""),
            "metadata": {"support_type": "context_chunk"},
        }

    def _spans(self, span_ids: list[str]) -> list[dict]:
        if not span_ids:
            return []
        ph = ",".join("?" for _ in span_ids)
        with self.db.connect() as con:
            rows = con.execute(f"SELECT * FROM token_spans WHERE id IN ({ph})", span_ids).fetchall()
        return rows_to_dicts(rows)


def _short_quote(text: str, limit: int = 360) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
