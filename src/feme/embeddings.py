from __future__ import annotations

import hashlib
import importlib.util
import math
import re
from typing import Any, Protocol


class EmbeddingProvider(Protocol):
    name: str
    version: str
    dimensions: int

    def embed_text(self, text: str) -> list[float]: ...


class EmbeddingRegistry:
    def __init__(self):
        self._providers: dict[str, EmbeddingProvider] = {}

    def register(self, provider: EmbeddingProvider) -> None:
        name = str(getattr(provider, "name", "")).strip()
        if not name:
            raise ValueError("Embedding provider must define a non-empty name")
        self._providers[name] = provider

    def get(self, name: str | None) -> EmbeddingProvider | None:
        if not isinstance(name, str) or not name.strip():
            return None
        return self._providers.get(name.strip())

    def names(self) -> list[str]:
        return sorted(self._providers.keys())


class HashingEmbedder:
    """Deterministic local embedding for demos/tests.

    This is not as strong as a real embedding model. It exists so the repository
    works without API keys or model downloads. Replace with sentence-transformers,
    OpenAI embeddings, or a local model when needed.
    """

    def __init__(self, dims: int = 256):
        self.dims = dims

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dims
        terms = re.findall(r"[a-zA-Z0-9_]+", text.lower())
        for term in terms:
            h = hashlib.blake2b(term.encode("utf-8"), digest_size=8).digest()
            n = int.from_bytes(h, "little")
            idx = n % self.dims
            sign = 1.0 if (n >> 8) & 1 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class HashingEmbeddingProvider:
    name = "hashing"
    version = "1.0.0"

    def __init__(self, dimensions: int = 256):
        self.dimensions = dimensions
        self._embedder = HashingEmbedder(dims=dimensions)

    def embed_text(self, text: str) -> list[float]:
        return self._embedder.embed(text)


def build_default_embedding_registry() -> EmbeddingRegistry:
    registry = EmbeddingRegistry()
    registry.register(HashingEmbeddingProvider())
    return registry


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


def embedding_runtime_capabilities(database: Any | None = None) -> dict[str, Any]:
    pgvector_python_available = _has_python_pgvector()
    pgvector_database_enabled = _has_pgvector_extension(database)
    registry = build_default_embedding_registry()
    provider = registry.get("hashing")
    mode = (
        "pgvector"
        if pgvector_python_available and pgvector_database_enabled
        else "hashing"
    )
    return {
        "provider": "hashing-embedding-v1",
        "provider_name": provider.name if provider else "hashing",
        "provider_version": provider.version if provider else "1.0.0",
        "provider_dimensions": provider.dimensions if provider else 256,
        "pgvector_python_available": pgvector_python_available,
        "pgvector_database_enabled": pgvector_database_enabled,
        "mode": mode,
    }


def _has_python_pgvector() -> bool:
    return importlib.util.find_spec("pgvector") is not None


def _has_pgvector_extension(database: Any | None) -> bool:
    if database is None:
        return False
    if str(getattr(database, "backend", "sqlite")).lower() != "postgres":
        return False
    try:
        with database.connect() as con:
            row = con.execute(
                "SELECT 1 AS ok FROM pg_extension WHERE extname = ? LIMIT 1",
                ("vector",),
            ).fetchone()
        return bool(row)
    except Exception:
        return False
