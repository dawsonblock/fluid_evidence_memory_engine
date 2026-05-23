from __future__ import annotations

import hashlib
import importlib.util
import math
import re
from typing import Any


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


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


def embedding_runtime_capabilities(database: Any | None = None) -> dict[str, Any]:
    pgvector_python_available = _has_python_pgvector()
    pgvector_database_enabled = _has_pgvector_extension(database)
    mode = (
        "pgvector"
        if pgvector_python_available and pgvector_database_enabled
        else "hashing"
    )
    return {
        "provider": "hashing-embedding-v1",
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
