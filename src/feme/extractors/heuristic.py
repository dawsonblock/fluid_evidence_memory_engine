from __future__ import annotations

from typing import Any


class HeuristicExtractorProvider:
    name = "heuristic"
    version = "2.0.0"

    def extract(
        self,
        chunk_text: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        # The heuristic provider is implemented in claim_extractor.py.
        # This registry entry is only for provider discoverability.
        return {"claims": []}
