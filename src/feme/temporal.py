from __future__ import annotations

import re
from contextlib import nullcontext
from datetime import date

from .db import Database, rows_to_dicts
from .utils import json_dumps, new_id, now_iso

ISO_DATE_RE = re.compile(r"\b(20\d{2}|19\d{2})[-/](0?[1-9]|1[0-2])[-/](0?[1-9]|[12]\d|3[01])\b")
MONTH_DATE_RE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+([0-3]?\d),\s+(20\d{2}|19\d{2})\b",
    flags=re.IGNORECASE,
)
MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
    start=1,
)}


def extract_dates(text: str) -> list[dict]:
    out: list[dict] = []
    for m in ISO_DATE_RE.finditer(text):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            iso = date(y, mo, d).isoformat()
        except ValueError:
            continue
        out.append({"date_text": m.group(0), "event_date": iso, "char_start": m.start(), "char_end": m.end(), "precision": "day"})
    for m in MONTH_DATE_RE.finditer(text):
        mo = MONTHS[m.group(1).lower()]
        d, y = int(m.group(2)), int(m.group(3))
        try:
            iso = date(y, mo, d).isoformat()
        except ValueError:
            continue
        out.append({"date_text": m.group(0), "event_date": iso, "char_start": m.start(), "char_end": m.end(), "precision": "day"})
    out.sort(key=lambda x: (x["char_start"], x["char_end"]))
    # de-dupe overlapping matches
    deduped: list[dict] = []
    seen = set()
    for item in out:
        key = (item["event_date"], item["char_start"], item["char_end"])
        if key not in seen:
            deduped.append(item)
            seen.add(key)
    return deduped


class TimelineManager:
    def __init__(self, db: Database):
        self.db = db

    def build_for_evidence(
        self, evidence_id: str, *, con=None, autocommit: bool = True
    ) -> list[dict]:
        created: list[dict] = []
        now = now_iso()
        con_ctx = nullcontext(con) if con is not None else self.db.connect()
        with con_ctx as active_con:
            chunks = active_con.execute(
                "SELECT tc.*, ts.id AS span_id FROM text_chunks tc LEFT JOIN token_spans ts ON ts.chunk_id = tc.id WHERE tc.evidence_id = ? ORDER BY tc.chunk_index",
                (evidence_id,),
            ).fetchall()
            for chunk in chunks:
                for item in extract_dates(chunk["text"]):
                    absolute_start = int(chunk["char_start"]) + int(item["char_start"])
                    absolute_end = int(chunk["char_start"]) + int(item["char_end"])
                    event_id = new_id("time")
                    description = _sentence_around(chunk["text"], item["char_start"])
                    active_con.execute(
                        """
                        INSERT OR IGNORE INTO timeline_events
                        (id, project_id, evidence_id, claim_id, span_id, event_date, date_precision, description, confidence, created_at, metadata_json)
                        SELECT ?, es.project_id, ?, NULL, ?, ?, ?, ?, ?, ?, ?
                        FROM evidence_sources es WHERE es.id = ?
                        """,
                        (
                            event_id,
                            evidence_id,
                            chunk["span_id"],
                            item["event_date"],
                            item["precision"],
                            description,
                            0.65,
                            now,
                            json_dumps({"date_text": item["date_text"], "char_start": absolute_start, "char_end": absolute_end, "extractor": "temporal-v0.4"}),
                            evidence_id,
                        ),
                    )
                    created.append({"id": event_id, "event_date": item["event_date"], "description": description, "span_id": chunk["span_id"]})
            if autocommit:
                active_con.commit()
        return created

    def rebuild_project(self, *, project_id: str = "default", clear_existing: bool = True) -> dict:
        with self.db.connect() as con:
            if clear_existing:
                con.execute("DELETE FROM timeline_events WHERE project_id = ?", (project_id,))
            evidence_ids = [r["id"] for r in con.execute("SELECT id FROM evidence_sources WHERE project_id = ?", (project_id,)).fetchall()]
            con.commit()
        count = 0
        for evidence_id in evidence_ids:
            count += len(self.build_for_evidence(evidence_id))
        return {"project_id": project_id, "evidence_count": len(evidence_ids), "timeline_events": count}

    def list(self, *, project_id: str = "default", limit: int = 100) -> list[dict]:
        with self.db.connect() as con:
            rows = con.execute(
                """
                SELECT te.*, es.title, es.source_type
                FROM timeline_events te
                LEFT JOIN evidence_sources es ON es.id = te.evidence_id
                WHERE te.project_id = ?
                ORDER BY te.event_date, te.created_at
                LIMIT ?
                """,
                (project_id, limit),
            ).fetchall()
        return rows_to_dicts(rows)


def _sentence_around(text: str, idx: int) -> str:
    start = max(text.rfind(".", 0, idx), text.rfind("\n", 0, idx))
    end_candidates = [p for p in [text.find(".", idx), text.find("\n", idx)] if p != -1]
    end = min(end_candidates) if end_candidates else min(len(text), idx + 220)
    return text[start + 1 : end + 1].strip()[:500]
