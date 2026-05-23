from feme.extractors.registry import ExtractorRegistry, build_default_registry


class _Provider:
    name = "custom"
    version = "1.2.3"

    def extract(
        self, chunk_text: str, metadata: dict[str, object]
    ) -> dict[str, object]:
        return {"claims": []}


def test_registry_register_and_get_provider():
    registry = ExtractorRegistry()
    registry.register(_Provider())

    provider = registry.get("custom")
    assert provider is not None
    assert provider.name == "custom"
    assert provider.version == "1.2.3"


def test_default_registry_contains_builtin_structured_providers():
    registry = build_default_registry()

    json_static = registry.get("json_static")
    llm_stub = registry.get("llm_stub")

    assert json_static is not None
    assert llm_stub is not None
    assert json_static.version == "0.1.0"
