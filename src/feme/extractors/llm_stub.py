from __future__ import annotations

from typing import Any


class LlmStubExtractorProvider:
    name = "llm_stub"
    version = "0.0.1"

    def extract(
        self,
        chunk_text: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        raise RuntimeError("llm_stub provider is not implemented")
