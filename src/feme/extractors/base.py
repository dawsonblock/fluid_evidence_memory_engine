from __future__ import annotations

from typing import Any, Protocol


class ExtractorProvider(Protocol):
    name: str
    version: str

    def extract(
        self,
        chunk_text: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]: ...
