from __future__ import annotations

from pathlib import Path
from typing import Any

from feme.claim_extractor import extract_candidates_from_chunk
from feme.spans import validate_span
from feme.utils import json_loads


FIXTURES = [
    "tests/fixtures/extraction/project_decisions.jsonl",
    "tests/fixtures/extraction/multi_claim_documents.jsonl",
    "tests/fixtures/extraction/legal_style_claims.jsonl",
    "tests/fixtures/extraction/contradiction_claims.jsonl",
    "tests/fixtures/extraction/inference_vs_direct.jsonl",
    "tests/fixtures/extraction/messy_formatting.jsonl",
]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        payload = json_loads(line, default={})
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def test_all_extracted_claims_have_valid_support_spans():
    for fixture_path in FIXTURES:
        rows = _read_jsonl(Path(fixture_path))
        for idx, row in enumerate(rows):
            text = str(row.get("text") or "")
            chunk = {
                "id": f"chunk_{idx}",
                "evidence_id": f"ev_{idx}",
                "text": text,
                "chunk_index": 0,
                "char_start": 0,
                "token_start": 0,
                "source_quality": 0.95,
                "source_type": "official_record",
                "review_required": 0,
                "span_id": None,
            }
            candidates = extract_candidates_from_chunk(
                chunk,
                extractor_mode="heuristic",
            )
            for candidate in candidates:
                assert isinstance(candidate.support_char_start, int)
                assert isinstance(candidate.support_char_end, int)
                assert isinstance(candidate.support_quote_text, str)
                assert validate_span(
                    text,
                    candidate.support_char_start,
                    candidate.support_char_end,
                    candidate.support_quote_text,
                )
