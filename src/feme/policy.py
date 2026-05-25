from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .sensitive import sensitivity_score
from .utils import clamp


@dataclass(frozen=True)
class MemoryPolicy:
    durable_save_threshold: float = 0.72
    session_save_threshold: float = 0.48
    human_review_privacy_threshold: float = 0.85
    explicit_override_threshold: float = 0.85
    near_duplicate_threshold: float = 0.92
    inference_review_source_quality: float = 0.40
    stale_after_days: int = 180
    salience_decay_per_run: float = 0.03
    minimum_active_salience: float = 0.12
    source_quality: dict[str, float] = field(default_factory=dict)
    sensitive_terms: tuple[str, ...] = (
        "health",
        "diagnosis",
        "medication",
        "religion",
        "political",
        "sexual",
        "password",
        "api key",
        "private key",
        "sin",
        "social insurance",
    )

    @classmethod
    def default(cls) -> "MemoryPolicy":
        return cls(
            source_quality={
                "court_record": 0.95,
                "official_record": 0.95,
                "statute": 0.95,
                "legal_xml": 0.95,
                "email": 0.75,
                "uploaded_pdf": 0.75,
                "document": 0.75,
                "log": 0.70,
                "user_statement": 0.55,
                "note": 0.55,
                "chat": 0.55,
                "ai_summary": 0.25,
                "inference": 0.25,
            }
        )

    @classmethod
    def from_file(cls, path: str | Path | None) -> "MemoryPolicy":
        base = cls.default()
        if not path:
            return base
        p = Path(path)
        if not p.exists():
            return base
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return cls(
            durable_save_threshold=float(
                raw.get("durable_save_threshold", base.durable_save_threshold)
            ),
            session_save_threshold=float(
                raw.get("session_save_threshold", base.session_save_threshold)
            ),
            human_review_privacy_threshold=float(
                raw.get(
                    "human_review_privacy_threshold",
                    base.human_review_privacy_threshold,
                )
            ),
            explicit_override_threshold=float(
                raw.get("explicit_override_threshold", base.explicit_override_threshold)
            ),
            near_duplicate_threshold=float(
                raw.get("near_duplicate_threshold", base.near_duplicate_threshold)
            ),
            inference_review_source_quality=float(
                raw.get(
                    "inference_review_source_quality",
                    base.inference_review_source_quality,
                )
            ),
            stale_after_days=int(raw.get("stale_after_days", base.stale_after_days)),
            salience_decay_per_run=float(
                raw.get("salience_decay_per_run", base.salience_decay_per_run)
            ),
            minimum_active_salience=float(
                raw.get("minimum_active_salience", base.minimum_active_salience)
            ),
            source_quality={
                **base.source_quality,
                **dict(raw.get("source_quality", {})),
            },
            sensitive_terms=tuple(raw.get("sensitive_terms", base.sensitive_terms)),
        )

    def quality_for_source(self, source_type: str) -> float:
        return float(self.source_quality.get(source_type.lower(), 0.50))

    def privacy_sensitivity_for_text(self, text: str) -> float:
        return max(_legacy_privacy_score(text), sensitivity_score(text))

    def as_dict(self) -> dict[str, Any]:
        return {
            "durable_save_threshold": self.durable_save_threshold,
            "session_save_threshold": self.session_save_threshold,
            "human_review_privacy_threshold": self.human_review_privacy_threshold,
            "explicit_override_threshold": self.explicit_override_threshold,
            "near_duplicate_threshold": self.near_duplicate_threshold,
            "inference_review_source_quality": self.inference_review_source_quality,
            "stale_after_days": self.stale_after_days,
            "salience_decay_per_run": self.salience_decay_per_run,
            "minimum_active_salience": self.minimum_active_salience,
            "source_quality": self.source_quality,
            "sensitive_terms": list(self.sensitive_terms),
        }


def _legacy_privacy_score(text: str) -> float:
    lowered = text.lower()
    score = 0.0
    for marker in [
        "password",
        "medical",
        "diagnosis",
        "sin",
        "social insurance",
        "address",
        "credit card",
        "bank",
    ]:
        if marker in lowered:
            score += 0.2
    return clamp(score, 0.0, 1.0)
