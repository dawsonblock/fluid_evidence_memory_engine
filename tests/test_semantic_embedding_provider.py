"""Tests for SentenceTransformersEmbeddingProvider in feme.embeddings."""
from __future__ import annotations

import importlib.util

import pytest

from feme.embeddings import (
    EmbeddingRegistry,
    SentenceTransformersEmbeddingProvider,
)

HAS_ST = importlib.util.find_spec("sentence_transformers") is not None


# ---------------------------------------------------------------------------
# Attribute / interface tests (always run, no model download needed)
# ---------------------------------------------------------------------------

def test_provider_name():
    p = SentenceTransformersEmbeddingProvider()
    assert p.name == "sentence-transformers"


def test_provider_version():
    p = SentenceTransformersEmbeddingProvider()
    assert p.version == "0.8.2"


def test_default_model_name():
    p = SentenceTransformersEmbeddingProvider()
    assert p._model_name == "all-MiniLM-L6-v2"


def test_custom_model_name():
    p = SentenceTransformersEmbeddingProvider("paraphrase-MiniLM-L3-v2")
    assert p._model_name == "paraphrase-MiniLM-L3-v2"


def test_normalize_default_true():
    p = SentenceTransformersEmbeddingProvider()
    assert p._normalize is True


def test_normalize_false():
    p = SentenceTransformersEmbeddingProvider(normalize=False)
    assert p._normalize is False


def test_device_default_none():
    p = SentenceTransformersEmbeddingProvider()
    assert p._device is None


def test_device_kwarg():
    p = SentenceTransformersEmbeddingProvider(device="cpu")
    assert p._device == "cpu"


def test_model_not_loaded_at_construction():
    p = SentenceTransformersEmbeddingProvider()
    assert p._model is None


def test_satisfies_embedding_provider_protocol():
    """Provider has name, version, dimensions, embed_text — duck-type check."""
    p = SentenceTransformersEmbeddingProvider()
    assert hasattr(p, "name")
    assert hasattr(p, "version")
    assert hasattr(p, "dimensions")
    assert callable(p.embed_text)


def test_can_register_in_registry():
    reg = EmbeddingRegistry()
    p = SentenceTransformersEmbeddingProvider()
    reg.register(p)
    assert "sentence-transformers" in reg.names()


def test_get_from_registry():
    reg = EmbeddingRegistry()
    reg.register(SentenceTransformersEmbeddingProvider())
    retrieved = reg.get("sentence-transformers")
    assert retrieved is not None
    assert retrieved.name == "sentence-transformers"


# ---------------------------------------------------------------------------
# ImportError path (only if sentence-transformers is NOT installed)
# ---------------------------------------------------------------------------

def test_embed_text_raises_import_error_when_not_installed(monkeypatch):
    real_find_spec = importlib.util.find_spec

    def _fake_find_spec(name: str, package=None):
        if name == "sentence_transformers":
            return None
        return real_find_spec(name, package)

    monkeypatch.setattr(importlib.util, "find_spec", _fake_find_spec)
    p = SentenceTransformersEmbeddingProvider()
    with pytest.raises(ImportError, match="sentence-transformers"):
        p.embed_text("hello world")


def test_dimensions_returns_default_without_loading_model():
    """dimensions is accessible at construction time, returns pre-configured default."""
    p = SentenceTransformersEmbeddingProvider()
    assert p.dimensions == 384


def test_dimensions_custom_default():
    p = SentenceTransformersEmbeddingProvider(dimensions=768)
    assert p.dimensions == 768


# ---------------------------------------------------------------------------
# Live tests (only if sentence-transformers IS installed)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not HAS_ST, reason="sentence-transformers not installed"
)
def test_embed_text_returns_list_of_floats():
    p = SentenceTransformersEmbeddingProvider()
    result = p.embed_text("FEME stores memory in PostgreSQL.")
    assert isinstance(result, list)
    assert all(isinstance(v, float) for v in result)


@pytest.mark.skipif(
    not HAS_ST, reason="sentence-transformers not installed"
)
def test_embed_text_returns_correct_dimensions():
    p = SentenceTransformersEmbeddingProvider()
    result = p.embed_text("test")
    assert len(result) == p.dimensions


@pytest.mark.skipif(
    not HAS_ST, reason="sentence-transformers not installed"
)
def test_normalized_vector_unit_length():
    import math
    p = SentenceTransformersEmbeddingProvider(normalize=True)
    vec = p.embed_text("normalization test")
    norm = math.sqrt(sum(v * v for v in vec))
    assert abs(norm - 1.0) < 1e-4
