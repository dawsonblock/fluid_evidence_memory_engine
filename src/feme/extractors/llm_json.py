"""LLM-backed JSON extractor for FEME.

Calls an OpenAI-compatible chat completion endpoint and parses the response
as a ``claim-extraction-v1`` payload.  Configure via environment variables:

    FEME_EXTRACTOR_API_BASE   – base URL, e.g. ``https://api.openai.com/v1``
    FEME_EXTRACTOR_API_KEY    – bearer token (required)
    FEME_EXTRACTOR_MODEL      – model name, default ``gpt-4o-mini``
    FEME_EXTRACTOR_TIMEOUT    – HTTP timeout in seconds, default ``30``

Raises
------
LLMExtractorNotConfiguredError
    When ``FEME_EXTRACTOR_API_KEY`` is absent or empty.
"""
from __future__ import annotations

import json
import os
from typing import Any


class LLMExtractorNotConfiguredError(RuntimeError):
    """Raised when the LLM extractor lacks required configuration."""


_SYSTEM_PROMPT = """\
You are a structured knowledge extraction assistant.
Given a text chunk, extract factual claims in JSON format.
Return ONLY valid JSON matching the claim-extraction-v1 schema:
{
  "claims": [
    {
      "subject": "<subject string>",
      "predicate": "<predicate string>",
      "object": "<object string>",
      "claim_text": "<full claim sentence>",
      "support_char_start": <int>,
      "support_char_end": <int>,
      "support_quote_text": "<exact verbatim substring>",
            "support_relation": "supports|contradicts|corroborates|other support label",
            "evidence_kind": "direct|inference|summary|unknown",
      "confidence": <0.0-1.0>,
      "memory_type": "project_decision|evidence_claim|inference|correction|unknown"
    }
  ]
}
All char offsets are 0-based character positions into the supplied chunk text.
support_quote_text MUST be the exact verbatim substring chunk_text[support_char_start:support_char_end].
support_relation describes how the evidence link should be labeled.
evidence_kind describes whether the claim is direct evidence, inference, summary, or unknown.
Do not emit legacy evidence_relation unless explicitly asked for backward compatibility.
Return an empty claims list when no claims can be extracted.
"""


class LLMJsonExtractor:
    """Extractor that calls an OpenAI-compatible API to produce claim-extraction-v1 JSON."""

    name = "llm_json"
    version = "0.1.0"

    def __init__(
        self,
        *,
        api_base: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self._api_base = (
            api_base
            or os.environ.get("FEME_EXTRACTOR_API_BASE", "https://api.openai.com/v1")
        ).rstrip("/")
        self._api_key = api_key or os.environ.get("FEME_EXTRACTOR_API_KEY", "")
        self._model = model or os.environ.get("FEME_EXTRACTOR_MODEL", "gpt-4o-mini")
        raw_timeout = timeout or os.environ.get("FEME_EXTRACTOR_TIMEOUT", "30")
        try:
            self._timeout = float(raw_timeout)
        except (TypeError, ValueError):
            self._timeout = 30.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def provider_metadata(self) -> dict[str, Any]:
        """Return static provider metadata included in extractor audit rows."""
        return {
            "llm_api_base": self._api_base,
            "llm_model": self._model,
            "llm_timeout": self._timeout,
        }

    def extract(
        self,
        chunk_text: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """Call the LLM endpoint and return a claim-extraction-v1 payload dict."""
        if not self._api_key:
            raise LLMExtractorNotConfiguredError(
                "FEME_EXTRACTOR_API_KEY is not set; cannot use llm_json extractor"
            )

        request_body = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Extract claims from the following text:\n\n{chunk_text}",
                },
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"},
        }

        raw = self._post_chat_completion(request_body)
        return self._parse_response(raw)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _post_chat_completion(self, body: dict[str, Any]) -> str:
        url = f"{self._api_base}/chat/completions"
        payload_bytes = json.dumps(body).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            import httpx  # type: ignore[import]

            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(url, content=payload_bytes, headers=headers)
                response.raise_for_status()
                data = response.json()
        except ImportError:
            data = self._post_via_urllib(url, payload_bytes, headers)

        choices = data.get("choices") or []
        if not choices:
            return "{}"
        message = choices[0].get("message") or {}
        return str(message.get("content") or "{}")

    def _post_via_urllib(
        self,
        url: str,
        payload_bytes: bytes,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        import urllib.request

        req = urllib.request.Request(url, data=payload_bytes, method="POST")
        for k, v in headers.items():
            req.add_header(k, v)
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:  # noqa: S310
            body = resp.read()
            if isinstance(body, bytes):
                body = body.decode("utf-8")
            return json.loads(body)

    def _parse_response(self, content: str) -> dict[str, Any]:
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, ValueError):
            return {"claims": []}
        if not isinstance(parsed, dict):
            return {"claims": []}
        if "claims" not in parsed and "candidates" not in parsed:
            # The model may have returned a single-level list — wrap it.
            if isinstance(parsed, list):
                return {"claims": parsed}
            return {"claims": []}
        return parsed
