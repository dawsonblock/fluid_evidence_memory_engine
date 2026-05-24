"""Tests for the extractor repair module and LLMJsonExtractor."""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from feme.extractors.llm_json import (
    LLMExtractorNotConfiguredError,
    LLMJsonExtractor,
    _SYSTEM_PROMPT,
)
from feme.extractors.repair import attempt_repair, _strip_code_fence, _try_parse


# ---------------------------------------------------------------------------
# _strip_code_fence
# ---------------------------------------------------------------------------

class TestStripCodeFence:
    def test_strips_json_fence(self):
        text = "```json\n{\"claims\": []}\n```"
        assert _strip_code_fence(text) == '{"claims": []}'

    def test_strips_plain_fence(self):
        text = "```\n{\"claims\": []}\n```"
        assert _strip_code_fence(text) == '{"claims": []}'

    def test_noop_when_no_fence(self):
        text = '{"claims": []}'
        assert _strip_code_fence(text) == text


# ---------------------------------------------------------------------------
# _try_parse
# ---------------------------------------------------------------------------

class TestTryParse:
    def test_parses_valid_claims_dict(self):
        text = '{"claims": []}'
        result = _try_parse(text)
        assert result == {"claims": []}

    def test_parses_candidates_dict(self):
        text = '{"candidates": [{"subject": "x"}]}'
        result = _try_parse(text)
        assert result is not None
        assert "candidates" in result

    def test_returns_none_on_invalid_json(self):
        assert _try_parse("{not valid}") is None

    def test_returns_none_on_list(self):
        assert _try_parse("[1, 2, 3]") is None

    def test_returns_none_when_no_claims_key(self):
        assert _try_parse('{"foo": "bar"}') is None


# ---------------------------------------------------------------------------
# attempt_repair – fast-path fixes
# ---------------------------------------------------------------------------

class TestAttemptRepairFastPath:
    def test_repairs_code_fenced_json(self):
        fenced = '```json\n{"claims": []}\n```'
        mock_extractor = MagicMock()
        result = attempt_repair(fenced, mock_extractor)
        assert result == {"claims": []}
        mock_extractor.extract.assert_not_called()

    def test_repairs_whitespace_wrapped_json(self):
        padded = '   {"claims": [{"subject": "a"}]}   '
        mock_extractor = MagicMock()
        result = attempt_repair(padded, mock_extractor)
        assert result is not None
        assert "claims" in result
        mock_extractor.extract.assert_not_called()


# ---------------------------------------------------------------------------
# attempt_repair – extractor-assisted repair
# ---------------------------------------------------------------------------

class TestAttemptRepairViaExtractor:
    def _make_extractor(self, response: Any) -> MagicMock:
        extractor = MagicMock()
        extractor.extract.return_value = response
        return extractor

    def test_returns_repaired_dict_from_extractor(self):
        good = {"claims": [{"subject": "FEME", "predicate": "uses", "object": "PostgreSQL"}]}
        extractor = self._make_extractor(good)
        result = attempt_repair("{broken", extractor, max_attempts=1)
        assert result == good
        assert extractor.extract.call_count == 1

    def test_passes_repair_metadata_to_extractor(self):
        good = {"claims": []}
        extractor = self._make_extractor(good)
        attempt_repair("{broken", extractor, max_attempts=1)
        _, kwargs = extractor.extract.call_args
        assert kwargs.get("metadata") is not None or extractor.extract.call_args[0]
        # repair metadata should include is_repair_attempt
        call_args = extractor.extract.call_args
        meta_arg = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("metadata", {})
        assert meta_arg.get("is_repair_attempt") is True

    def test_returns_none_when_all_attempts_fail(self):
        extractor = MagicMock()
        extractor.extract.side_effect = RuntimeError("API down")
        result = attempt_repair("{definitely: broken", extractor, max_attempts=2)
        assert result is None
        assert extractor.extract.call_count == 2

    def test_returns_none_when_extractor_returns_bad_dict(self):
        extractor = self._make_extractor({"no_claims_key": True})
        # no fast-path parse, extractor returns unhelpful dict
        result = attempt_repair("{", extractor, max_attempts=1)
        assert result is None

    def test_max_attempts_respected(self):
        extractor = MagicMock()
        extractor.extract.side_effect = ValueError("bad")
        attempt_repair("{broken", extractor, max_attempts=3)
        assert extractor.extract.call_count == 3


# ---------------------------------------------------------------------------
# LLMJsonExtractor – configuration
# ---------------------------------------------------------------------------

class TestLLMJsonExtractorConfig:
    def test_name_and_version(self):
        extractor = LLMJsonExtractor(api_key="test")
        assert extractor.name == "llm_json"
        assert extractor.version == "0.1.0"

    def test_provider_metadata_contains_model(self):
        extractor = LLMJsonExtractor(api_key="test", model="gpt-4o")
        meta = extractor.provider_metadata()
        assert meta["llm_model"] == "gpt-4o"

    def test_provider_metadata_contains_api_base(self):
        extractor = LLMJsonExtractor(api_key="test", api_base="https://custom.example.com/v1")
        meta = extractor.provider_metadata()
        assert "custom.example.com" in meta["llm_api_base"]

    def test_raises_not_configured_when_no_api_key(self, monkeypatch):
        monkeypatch.delenv("FEME_EXTRACTOR_API_KEY", raising=False)
        extractor = LLMJsonExtractor()
        with pytest.raises(LLMExtractorNotConfiguredError):
            extractor.extract("some text", {})

    def test_raises_not_configured_empty_api_key_env(self, monkeypatch):
        monkeypatch.setenv("FEME_EXTRACTOR_API_KEY", "")
        extractor = LLMJsonExtractor()
        with pytest.raises(LLMExtractorNotConfiguredError):
            extractor.extract("some text", {})

    def test_reads_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("FEME_EXTRACTOR_API_KEY", "env-key-123")
        extractor = LLMJsonExtractor()
        assert extractor._api_key == "env-key-123"

    def test_constructor_api_key_takes_precedence_over_env(self, monkeypatch):
        monkeypatch.setenv("FEME_EXTRACTOR_API_KEY", "env-key")
        extractor = LLMJsonExtractor(api_key="ctor-key")
        assert extractor._api_key == "ctor-key"

    def test_system_prompt_uses_split_relation_fields(self):
        assert '"support_relation"' in _SYSTEM_PROMPT
        assert '"evidence_kind"' in _SYSTEM_PROMPT
        assert 'legacy evidence_relation' in _SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# LLMJsonExtractor – response parsing
# ---------------------------------------------------------------------------

class TestLLMJsonExtractorParsing:
    def _extractor(self) -> LLMJsonExtractor:
        return LLMJsonExtractor(api_key="test-key")

    def test_parse_valid_claims_response(self):
        e = self._extractor()
        content = json.dumps({"claims": [{"subject": "FEME", "predicate": "uses", "object": "Postgres"}]})
        result = e._parse_response(content)
        assert "claims" in result
        assert len(result["claims"]) == 1

    def test_parse_invalid_json_returns_empty_claims(self):
        e = self._extractor()
        result = e._parse_response("{definitely not json")
        assert result == {"claims": []}

    def test_parse_list_response_returns_empty_claims(self):
        e = self._extractor()
        result = e._parse_response("[1, 2, 3]")
        assert result == {"claims": []}

    def test_parse_empty_dict_response_returns_empty_claims(self):
        e = self._extractor()
        result = e._parse_response("{}")
        assert result == {"claims": []}

    def test_parse_candidates_key_accepted(self):
        e = self._extractor()
        content = json.dumps({"candidates": [{"x": 1}]})
        result = e._parse_response(content)
        assert "candidates" in result


# ---------------------------------------------------------------------------
# LLMJsonExtractor – in registry
# ---------------------------------------------------------------------------

def test_llm_json_extractor_in_default_registry():
    from feme.extractors.registry import build_default_registry
    registry = build_default_registry()
    provider = registry.get("llm_json")
    assert provider is not None
    assert provider.name == "llm_json"
