from __future__ import annotations

from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field


class ClaimStatus(str, Enum):
    active = "active"
    stale = "stale"
    disputed = "disputed"
    superseded = "superseded"
    rejected = "rejected"
    archived = "archived"
    pending_review = "pending_review"


class MemoryType(str, Enum):
    identity = "identity"
    project_decision = "project_decision"
    evidence_claim = "evidence_claim"
    procedure = "procedure"
    correction = "correction"
    contradiction = "contradiction"
    inference = "inference"
    transient = "transient"
    unknown = "unknown"


class MemoryLevel(str, Enum):
    do_not_save = "do_not_save"
    session_memory = "session_memory"
    project_memory = "project_memory"
    core_memory = "core_memory"
    evidence_memory = "evidence_memory"


class WriteDecision(str, Enum):
    save_new = "save_new"
    merge_with_existing = "merge_with_existing"
    update_existing = "update_existing"
    mark_disputed = "mark_disputed"
    mark_superseded = "mark_superseded"
    save_as_inference_only = "save_as_inference_only"
    session_only = "session_only"
    reject = "reject"
    needs_human_review = "needs_human_review"


class EvidenceSource(BaseModel):
    id: str
    project_id: str = "default"
    source_type: str
    title: str | None = None
    source_uri: str | None = None
    sha256: str
    captured_at: str
    review_status: str = "pending_review"
    metadata: dict[str, Any] = Field(default_factory=dict)


class TextChunk(BaseModel):
    id: str
    evidence_id: str
    snapshot_id: str
    chunk_index: int
    char_start: int
    char_end: int
    token_start: int
    token_end: int
    text: str
    token_count: int
    salience: float = 0.5
    source_quality: float = 0.5
    created_at: str


class TokenSpan(BaseModel):
    id: str
    evidence_id: str
    chunk_id: str
    char_start: int
    char_end: int
    token_start: int
    token_end: int
    text_sha256: str
    text: str
    created_at: str


class ClaimCandidate(BaseModel):
    subject: str
    predicate: str
    object: str
    claim_text: str
    memory_type: MemoryType = MemoryType.unknown
    memory_level: MemoryLevel = MemoryLevel.project_memory
    confidence: float = 0.5
    salience: float = 0.5
    source_quality: float = 0.5
    user_explicitness: float = 0.0
    long_term_usefulness: float = 0.5
    project_relevance: float = 0.5
    actionability: float = 0.5
    contradiction_value: float = 0.0
    privacy_sensitivity: float = 0.0
    uncertainty: float = 0.2
    triviality: float = 0.0
    short_livedness: float = 0.0
    evidence_id: str | None = None
    chunk_id: str | None = None
    span_id: str | None = None
    support_char_start: int | None = None
    support_char_end: int | None = None
    support_token_start: int | None = None
    support_token_end: int | None = None
    support_quote_text: str | None = None
    support_relation: str = "supports"
    evidence_kind: str = "unknown"
    evidence_relation: str = "unknown"
    valid_from: str | None = None
    valid_to: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryClaim(BaseModel):
    id: str
    project_id: str = "default"
    subject: str
    predicate: str
    object: str
    claim_text: str
    memory_type: MemoryType
    memory_level: MemoryLevel
    status: ClaimStatus = ClaimStatus.active
    confidence: float = 0.5
    salience: float = 0.5
    source_quality: float = 0.5
    valid_from: str | None = None
    valid_to: str | None = None
    created_at: str
    updated_at: str
    last_touched: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class WriteDecisionResult(BaseModel):
    decision: WriteDecision
    memory_level: MemoryLevel
    save_score: float
    reasons: list[str] = Field(default_factory=list)
    matched_claim_id: str | None = None
    requires_review: bool = False


class RetrievalResult(BaseModel):
    kind: Literal["claim", "chunk"]
    id: str
    text: str
    score: float
    evidence_id: str | None = None
    claim_id: str | None = None
    chunk_id: str | None = None
    span_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContextPacket(BaseModel):
    question: str
    token_budget: int
    included: list[dict[str, Any]]
    excluded: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class VerificationReport(BaseModel):
    ok: bool
    risk_level: Literal["low", "medium", "high"]
    issue_count: int
    issues: list[dict[str, Any]] = Field(default_factory=list)
    checked_claim_ids: list[str] = Field(default_factory=list)
    checked_span_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    publication_blocked: bool = False


class EvaluationCase(BaseModel):
    id: str
    query: str
    expected_claim_ids: list[str] = Field(default_factory=list)
    expected_terms: list[str] = Field(default_factory=list)
    project_id: str = "default"
