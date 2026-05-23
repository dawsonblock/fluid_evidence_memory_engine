from __future__ import annotations

import re
from contextlib import nullcontext
from dataclasses import dataclass

from .db import Database
from .utils import new_id, normalize_key, now_iso


@dataclass(frozen=True)
class EntityMentionCandidate:
    name: str
    entity_type: str
    char_start: int
    char_end: int
    confidence: float = 0.60


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
DATE_RE = re.compile(r"\b(?:\d{4}-\d{2}-\d{2}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})\b", re.I)
ORG_RE = re.compile(r"\b[A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){0,4}\s+(?:Inc|Corp|Corporation|Ltd|LLC|Court|Ministry|Department|Bayshore|WCB)\b")
PERSONISH_RE = re.compile(r"\b[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){1,2}\b")


def extract_entities(text: str) -> list[EntityMentionCandidate]:
    found: list[EntityMentionCandidate] = []
    for m in EMAIL_RE.finditer(text):
        found.append(EntityMentionCandidate(m.group(0), "email", m.start(), m.end(), 0.95))
    for m in DATE_RE.finditer(text):
        found.append(EntityMentionCandidate(m.group(0), "date", m.start(), m.end(), 0.90))
    for m in ORG_RE.finditer(text):
        found.append(EntityMentionCandidate(m.group(0), "organization", m.start(), m.end(), 0.70))
    for m in PERSONISH_RE.finditer(text):
        # Avoid reclassifying likely org/date fragments when already covered.
        if any(_overlaps(m.start(), m.end(), x.char_start, x.char_end) for x in found):
            continue
        found.append(EntityMentionCandidate(m.group(0), "person_or_title", m.start(), m.end(), 0.55))
    return found


def persist_entities_for_chunk(
    db: Database,
    chunk: dict,
    span_id: str | None = None,
    *,
    con=None,
    autocommit: bool = True,
) -> list[str]:
    mentions = extract_entities(chunk.get("text", ""))
    ids: list[str] = []
    if not mentions:
        return ids
    now = now_iso()
    con_ctx = nullcontext(con) if con is not None else db.connect()
    with con_ctx as active_con:
        for mention in mentions:
            norm = normalize_key(mention.name)
            row = active_con.execute(
                "SELECT id FROM entities WHERE normalized_name = ? AND entity_type = ?",
                (norm, mention.entity_type),
            ).fetchone()
            if row:
                entity_id = row["id"]
            else:
                entity_id = new_id("ent")
                active_con.execute(
                    "INSERT INTO entities (id, name, normalized_name, entity_type, created_at) VALUES (?, ?, ?, ?, ?)",
                    (entity_id, mention.name, norm, mention.entity_type, now),
                )
            mention_id = new_id("ment")
            ids.append(mention_id)
            active_con.execute(
                """
                INSERT INTO entity_mentions
                (id, entity_id, evidence_id, chunk_id, span_id, char_start, char_end, mention_text, confidence, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mention_id,
                    entity_id,
                    chunk.get("evidence_id"),
                    chunk.get("id"),
                    span_id,
                    int(chunk.get("char_start", 0)) + mention.char_start,
                    int(chunk.get("char_start", 0)) + mention.char_end,
                    mention.name,
                    mention.confidence,
                    now,
                ),
            )
        if autocommit:
            active_con.commit()
    return ids


def _overlaps(a0: int, a1: int, b0: int, b1: int) -> bool:
    return max(a0, b0) < min(a1, b1)
