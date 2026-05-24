from __future__ import annotations

from .base import ExtractorProvider


class ExtractorRegistry:
    def __init__(self):
        self._providers: dict[str, ExtractorProvider] = {}

    def register(self, provider: ExtractorProvider) -> None:
        name = str(getattr(provider, "name", "")).strip()
        if not name:
            raise ValueError("Extractor provider must define a non-empty name")
        self._providers[name] = provider

    def get(self, name: str | None) -> ExtractorProvider | None:
        if not isinstance(name, str) or not name.strip():
            return None
        return self._providers.get(name.strip())

    def names(self) -> list[str]:
        return sorted(self._providers.keys())


def build_default_registry() -> ExtractorRegistry:
    from .json_static import JsonStaticExtractorProvider
    from .llm_json import LLMJsonExtractor
    from .llm_stub import LlmStubExtractorProvider

    registry = ExtractorRegistry()
    registry.register(JsonStaticExtractorProvider())
    registry.register(LlmStubExtractorProvider())
    registry.register(LLMJsonExtractor())
    return registry
