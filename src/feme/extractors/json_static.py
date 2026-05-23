from __future__ import annotations

from typing import Any


class JsonStaticExtractorProvider:
    name = "json_static"
    version = "0.1.0"

    def extract(
        self,
        chunk_text: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        configured = (
            metadata.get("extractor_config") if isinstance(metadata, dict) else None
        )
        if not isinstance(configured, dict):
            return {"claims": []}

        payload = configured.get("claims")
        if isinstance(payload, list):
            return {"claims": payload}

        raw_payload = configured.get("payload")
        if isinstance(raw_payload, dict):
            return raw_payload
        return {"claims": []}
