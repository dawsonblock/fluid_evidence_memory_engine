from __future__ import annotations

from .models import ClaimCandidate
from .utils import clamp


def save_score(candidate: ClaimCandidate) -> float:
    positive = (
        0.22 * candidate.long_term_usefulness
        + 0.18 * candidate.user_explicitness
        + 0.16 * candidate.project_relevance
        + 0.14 * candidate.source_quality
        + 0.10 * candidate.actionability
        + 0.10 * candidate.contradiction_value
        + 0.10 * candidate.salience
    )
    negative = (
        0.20 * candidate.privacy_sensitivity
        + 0.20 * candidate.uncertainty
        + 0.25 * candidate.triviality
        + 0.25 * candidate.short_livedness
    )
    return clamp(positive - negative + 0.20)


def retrieval_score(
    semantic_similarity: float,
    keyword_score: float,
    source_quality: float,
    confidence: float,
    task_relevance: float,
    salience: float,
    recency: float,
    contradiction_penalty: float = 0.0,
    stale_penalty: float = 0.0,
    unsupported_ai_summary_penalty: float = 0.0,
) -> float:
    score = (
        0.25 * semantic_similarity
        + 0.20 * keyword_score
        + 0.15 * source_quality
        + 0.15 * confidence
        + 0.10 * task_relevance
        + 0.10 * salience
        + 0.05 * recency
        - contradiction_penalty
        - stale_penalty
        - unsupported_ai_summary_penalty
    )
    return clamp(score)
