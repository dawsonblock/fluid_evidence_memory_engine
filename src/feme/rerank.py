from __future__ import annotations

from .embeddings import HashingEmbedder, cosine
from .models import RetrievalResult


def diversify_results(
    query: str,
    results: list[RetrievalResult],
    *,
    top_k: int,
    lambda_relevance: float = 0.78,
) -> list[RetrievalResult]:
    """Maximal marginal relevance reranker.

    It keeps high-scoring results, but penalizes near-duplicate chunks/claims so the context packet
    carries broader evidence coverage instead of five copies of the same statement.
    """
    if len(results) <= top_k:
        return results[:top_k]
    embedder = HashingEmbedder()
    vectors = {r.id: embedder.embed(r.text) for r in results}
    selected: list[RetrievalResult] = []
    remaining = list(results)
    while remaining and len(selected) < top_k:
        best = None
        best_score = float("-inf")
        for r in remaining:
            redundancy = 0.0
            if selected:
                redundancy = max(cosine(vectors[r.id], vectors[s.id]) for s in selected)
            mmr = lambda_relevance * r.score - (1.0 - lambda_relevance) * redundancy
            if mmr > best_score:
                best = r
                best_score = mmr
        if best is None:
            break
        selected.append(best)
        remaining.remove(best)
    return selected
