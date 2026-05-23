from __future__ import annotations

import hashlib
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

from .claim_extractor import extract_candidates_for_evidence
from .config import get_settings
from .extractors import build_default_registry
from .context_builder import ContextBuilder
from .contradiction import ContradictionEngine
from .evidence import EvidenceIngestor
from .export_import import ProjectExporter
from .lifecycle import MemoryLifecycleManager
from .retrieval import RetrievalPlanner
from .verifier import AnswerVerifier
from .write_governor import MemoryWriteGovernor
from .projects import ProjectManager
from .provenance import ProvenanceGraph
from .backup import BackupManager
from .review import ReviewQueue
from .integrity import IntegrityChecker
from .source_registry import SourceRegistry
from .temporal import TimelineManager
from .citations import CitationManager
from .consolidation import MemoryConsolidator
from .retention import RetentionManager
from .maintenance import MaintenanceManager
from .answer_builder import GroundedAnswerBuilder
from .runtime_pipeline import TransactionalIngestionPipeline
from .ledger import MemoryLedger
from .claim_canonicalizer import ClaimCanonicalizer
from .retrieval_eval_suite import RetrievalEvalSuite
from .runtime import make_database, runtime_health

app = FastAPI(title="Fluid Evidence Memory Engine", version="0.7.5")
settings = get_settings()
database = make_database()
database.init()

ROLE_LEVELS = {
    "viewer": 10,
    "reviewer": 20,
    "editor": 30,
    "admin": 40,
}


def _principal_hash(api_key: str | None) -> str:
    if not api_key:
        return ""
    digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    return digest[:16]


def _audit_api_auth_decision(
    *,
    request: Request,
    required_role: str,
    resolved_role: str | None,
    decision: str,
    detail: str,
    principal_hash: str,
) -> None:
    try:
        from .utils import new_id, now_iso

        with database.connect() as con:
            con.execute(
                """
                INSERT INTO api_request_audit
                (
                    id,
                    method,
                    path,
                    required_role,
                    resolved_role,
                    decision,
                    detail,
                    principal_hash,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_id("apiaudit"),
                    request.method,
                    request.url.path,
                    required_role,
                    resolved_role,
                    decision,
                    detail,
                    principal_hash,
                    now_iso(),
                ),
            )
            con.commit()
    except Exception:
        # Never block request flow if audit persistence is unavailable.
        return


def _auth_enabled() -> bool:
    auth_settings = get_settings()
    return bool(
        auth_settings.api_auth_required
        or auth_settings.api_key_admin
        or auth_settings.api_key_editor
        or auth_settings.api_key_reviewer
        or auth_settings.api_key_viewer
        or auth_settings.api_key_readonly
    )


def _role_for_api_key(api_key: str) -> str | None:
    auth_settings = get_settings()
    if auth_settings.api_key_admin and api_key == auth_settings.api_key_admin:
        return "admin"
    if (
        auth_settings.api_key_editor
        and api_key == auth_settings.api_key_editor
    ):
        return "editor"
    if (
        auth_settings.api_key_reviewer
        and api_key == auth_settings.api_key_reviewer
    ):
        return "reviewer"
    viewer_key = auth_settings.api_key_viewer or auth_settings.api_key_readonly
    if viewer_key and api_key == viewer_key:
        return "viewer"
    return None


def require_api_scope(
    required_role: str,
    api_key: str | None,
    request: Request,
) -> None:
    principal_hash = _principal_hash(api_key)
    if not _auth_enabled():
        _audit_api_auth_decision(
            request=request,
            required_role=required_role,
            resolved_role="anonymous",
            decision="bypassed",
            detail="auth_disabled",
            principal_hash=principal_hash,
        )
        return
    if not api_key:
        _audit_api_auth_decision(
            request=request,
            required_role=required_role,
            resolved_role=None,
            decision="denied",
            detail="missing_api_key",
            principal_hash=principal_hash,
        )
        raise HTTPException(status_code=401, detail="missing_api_key")
    key_role = _role_for_api_key(api_key)
    if key_role is None:
        _audit_api_auth_decision(
            request=request,
            required_role=required_role,
            resolved_role=None,
            decision="denied",
            detail="invalid_api_key",
            principal_hash=principal_hash,
        )
        raise HTTPException(status_code=403, detail="invalid_api_key")
    if ROLE_LEVELS[key_role] < ROLE_LEVELS[required_role]:
        _audit_api_auth_decision(
            request=request,
            required_role=required_role,
            resolved_role=key_role,
            decision="denied",
            detail="insufficient_api_scope",
            principal_hash=principal_hash,
        )
        raise HTTPException(status_code=403, detail="insufficient_api_scope")
    _audit_api_auth_decision(
        request=request,
        required_role=required_role,
        resolved_role=key_role,
        decision="allowed",
        detail="",
        principal_hash=principal_hash,
    )


def require_viewer_api_key(
    request: Request,
    x_feme_api_key: str | None = Header(default=None, alias="X-FEME-API-Key"),
) -> None:
    require_api_scope("viewer", x_feme_api_key, request)


def require_reviewer_api_key(
    request: Request,
    x_feme_api_key: str | None = Header(default=None, alias="X-FEME-API-Key"),
) -> None:
    require_api_scope("reviewer", x_feme_api_key, request)


def require_editor_api_key(
    request: Request,
    x_feme_api_key: str | None = Header(default=None, alias="X-FEME-API-Key"),
) -> None:
    require_api_scope("editor", x_feme_api_key, request)


def require_admin_api_key(
    request: Request,
    x_feme_api_key: str | None = Header(default=None, alias="X-FEME-API-Key"),
) -> None:
    require_api_scope("admin", x_feme_api_key, request)


class IngestRequest(BaseModel):
    text: str
    source_type: str = "note"
    title: str | None = None
    project_id: str = "default"
    extract_claims: bool = True
    extract_entities: bool = True
    extractor_mode: str | None = None
    extractor_provider: str | None = None
    extractor_schema_version: str | None = None
    allow_evidence_only_on_extractor_failure: bool = False


class SearchRequest(BaseModel):
    query: str
    project_id: str = "default"
    top_k: int = 10
    retrieval_mode: Literal["public", "internal"] | None = None
    include_pending_review: bool = False


class ContextRequest(BaseModel):
    question: str
    project_id: str = "default"
    token_budget: int = 12000
    retrieval_mode: Literal["public", "internal"] | None = None
    include_pending_review: bool = False


class ReviewActionRequest(BaseModel):
    claim_id: str
    action: str
    reviewer: str | None = None
    reason: str = ""


class ReviewEvidenceRequest(BaseModel):
    evidence_id: str
    action: str
    reviewer: str | None = None
    reason: str = ""


class VerifyAnswerRequest(BaseModel):
    question: str
    answer_text: str | None = None
    project_id: str = "default"
    token_budget: int = 12000
    retrieval_mode: Literal["public", "internal"] | None = None
    include_pending_review: bool = False


class SourceSetRequest(BaseModel):
    source_type: str
    project_id: str = "default"
    enabled: bool = True
    default_quality: float | None = None
    review_required: bool | None = None


class RedactEvidenceRequest(BaseModel):
    evidence_id: str
    actor: str | None = None
    reason: str = ""


class GovernedIngestRequest(BaseModel):
    text: str
    source_type: str = "note"
    title: str | None = None
    source_uri: str | None = None
    project_id: str = "default"
    actor: str | None = None
    extract_claims: bool = True
    extractor_mode: str | None = None
    extractor_provider: str | None = None
    extractor_schema_version: str | None = None
    allow_evidence_only_on_extractor_failure: bool = False


class EvalCaseRequest(BaseModel):
    query: str
    project_id: str = "default"
    expected_claim_ids: list[str] = []
    expected_terms: list[str] = []


@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": "0.7.5",
        "db_backend": settings.db_backend,
        "db_path": getattr(database, "path", settings.db_path),
        "runtime": runtime_health(database),
    }


@app.post("/ingest")
def ingest(req: IngestRequest, _auth: None = Depends(require_editor_api_key)):
    extractor_mode = req.extractor_mode or settings.extractor_mode
    extractor_provider = req.extractor_provider or settings.extractor_provider
    extractor_schema_version = (
        req.extractor_schema_version or settings.extractor_schema_version
    )
    strict_provider_invalid = extractor_mode == "json_strict" and (
        not isinstance(extractor_provider, str)
        or not extractor_provider.strip()
        or build_default_registry().get(extractor_provider) is None
    )
    if (
        strict_provider_invalid
        and not req.allow_evidence_only_on_extractor_failure
    ):
        raise HTTPException(
            status_code=400,
            detail="structured_extractor_unavailable",
        )
    result = EvidenceIngestor(database).ingest_text(
        req.text,
        source_type=req.source_type,
        title=req.title,
        project_id=req.project_id,
        extract_entities=req.extract_entities,
    )
    claim_results = []
    contradictions = []
    audit_warnings: list[str] = []
    if req.extract_claims:
        if (
            strict_provider_invalid
            and req.allow_evidence_only_on_extractor_failure
        ):
            return {
                "evidence": result,
                "claim_writes": [],
                "contradictions": [],
                "extractor_outcome": "strict_rejected",
                "reason": "structured_extractor_unavailable",
                "audit_warnings": [],
            }
        governor = MemoryWriteGovernor(database)
        contradiction = ContradictionEngine(database)
        candidates = extract_candidates_for_evidence(
            database,
            result["evidence_id"],
            extractor_mode=extractor_mode,
            extractor_provider=extractor_provider,
            extractor_schema_version=extractor_schema_version,
            require_extractor_audit=settings.require_extractor_audit,
            audit_warnings=audit_warnings,
        )
        for candidate in candidates:
            write = governor.commit_candidate(
                candidate,
                project_id=req.project_id,
            )
            if write.matched_claim_id:
                contradictions.extend(
                    contradiction.scan_new_claim(write.matched_claim_id)
                )
            claim_results.append(write.model_dump())
    return {
        "evidence": result,
        "claim_writes": claim_results,
        "contradictions": contradictions,
        "audit_warnings": audit_warnings,
    }


@app.post("/search")
def search(req: SearchRequest, _auth: None = Depends(require_viewer_api_key)):
    return [
        r.model_dump()
        for r in RetrievalPlanner(database).search(
            req.query,
            project_id=req.project_id,
            top_k=req.top_k,
            retrieval_mode=req.retrieval_mode,
            include_pending_review=req.include_pending_review,
        )
    ]


@app.post("/context")
def context(
    req: ContextRequest,
    _auth: None = Depends(require_viewer_api_key),
):
    return (
        ContextBuilder(database)
        .build(
            req.question,
            project_id=req.project_id,
            token_budget=req.token_budget,
            retrieval_mode=req.retrieval_mode,
            include_pending_review=req.include_pending_review,
        )
        .model_dump()
    )


@app.post("/verify")
def verify(
    req: VerifyAnswerRequest,
    _auth: None = Depends(require_viewer_api_key),
):
    packet = ContextBuilder(database).build(
        req.question,
        project_id=req.project_id,
        token_budget=req.token_budget,
        retrieval_mode=req.retrieval_mode,
        include_pending_review=req.include_pending_review,
    )
    verifier = AnswerVerifier(database)
    if req.answer_text:
        return verifier.verify_answer_text(
            packet,
            req.answer_text,
        ).model_dump()
    return verifier.verify_context(packet).model_dump()


@app.post("/lifecycle/decay")
def lifecycle_decay(
    project_id: str = "default", _auth: None = Depends(require_editor_api_key)
):
    return MemoryLifecycleManager(database).run_decay(project_id=project_id)


@app.get("/claims")
def claims(
    project_id: str = "default",
    limit: int = 50,
    _auth: None = Depends(require_viewer_api_key),
):
    with database.connect() as con:
        rows = con.execute(
            "SELECT * FROM memory_claims "
            "WHERE project_id = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (project_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


@app.get("/entities")
def entities(limit: int = 100, _auth: None = Depends(require_viewer_api_key)):
    with database.connect() as con:
        rows = con.execute(
            "SELECT e.*, COUNT(m.id) AS mention_count "
            "FROM entities e "
            "LEFT JOIN entity_mentions m ON m.entity_id = e.id "
            "GROUP BY e.id ORDER BY mention_count DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


@app.post("/export")
def export(
    project_id: str = "default",
    out_path: str = "feme_export.json",
    _auth: None = Depends(require_viewer_api_key),
):
    return ProjectExporter(database).export_project(project_id, out_path)


@app.get("/projects")
def list_projects(_auth: None = Depends(require_viewer_api_key)):
    return ProjectManager(database).list()


@app.get("/projects/{project_id}/stats")
def project_stats(
    project_id: str,
    _auth: None = Depends(require_viewer_api_key),
):
    return ProjectManager(database).stats(project_id)


@app.get("/review/pending")
def review_pending(
    project_id: str = "default",
    limit: int = 50,
    _auth: None = Depends(require_reviewer_api_key),
):
    return ReviewQueue(database).list_pending(
        project_id=project_id,
        limit=limit,
    )


@app.post("/review/action")
def review_action(
    req: ReviewActionRequest, _auth: None = Depends(require_reviewer_api_key)
):
    return ReviewQueue(database).act(
        req.claim_id, req.action, reviewer=req.reviewer, reason=req.reason
    )


@app.post("/review/evidence")
def review_evidence(
    req: ReviewEvidenceRequest, _auth: None = Depends(require_reviewer_api_key)
):
    return ReviewQueue(database).review_evidence(
        req.evidence_id, req.action, reviewer=req.reviewer, reason=req.reason
    )


@app.get("/claims/{claim_id}/trace")
def claim_trace(claim_id: str, _auth: None = Depends(require_viewer_api_key)):
    return ProvenanceGraph(database).trace_claim(claim_id)


@app.post("/integrity/check")
def integrity_check(
    project_id: str = "default", _auth: None = Depends(require_editor_api_key)
):
    return IntegrityChecker(database).run(project_id=project_id)


@app.post("/backup")
def backup(
    out_path: str = "feme_backup.sqlite",
    _auth: None = Depends(require_admin_api_key),
):
    return BackupManager(database).backup(out_path)


@app.get("/sources")
def source_list(
    project_id: str = "default", _auth: None = Depends(require_viewer_api_key)
):
    SourceRegistry(database).ensure_defaults(project_id=project_id)
    return SourceRegistry(database).list(project_id=project_id)


@app.post("/sources")
def source_set(
    req: SourceSetRequest,
    _auth: None = Depends(require_admin_api_key),
):
    return SourceRegistry(database).upsert(
        req.source_type,
        project_id=req.project_id,
        enabled=req.enabled,
        default_quality=req.default_quality,
        review_required=req.review_required,
    )


@app.post("/timeline/rebuild")
def timeline_rebuild(
    project_id: str = "default", _auth: None = Depends(require_editor_api_key)
):
    return TimelineManager(database).rebuild_project(project_id=project_id)


@app.get("/timeline")
def timeline(
    project_id: str = "default",
    limit: int = 100,
    _auth: None = Depends(require_viewer_api_key),
):
    return TimelineManager(database).list(project_id=project_id, limit=limit)


@app.post("/citations")
def citations(
    req: ContextRequest,
    persist: bool = False,
    _auth: None = Depends(require_viewer_api_key),
):
    packet = ContextBuilder(database).build(
        req.question,
        project_id=req.project_id,
        token_budget=req.token_budget,
        include_pending_review=req.include_pending_review,
    )
    return CitationManager(database).citations_for_context(
        packet,
        persist=persist,
    )


@app.post("/answer/scaffold")
def answer_scaffold(
    req: ContextRequest,
    _auth: None = Depends(require_viewer_api_key),
):
    return GroundedAnswerBuilder(database).build_scaffold(
        req.question,
        project_id=req.project_id,
        token_budget=req.token_budget,
        include_pending_review=req.include_pending_review,
    )


@app.post("/consolidate")
def consolidate(
    project_id: str = "default", _auth: None = Depends(require_editor_api_key)
):
    manager = MemoryConsolidator(database)
    result = manager.create_subject_capsules(project_id=project_id)
    result.update(manager.link_near_duplicate_claims(project_id=project_id))
    return result


@app.get("/capsules")
def capsules(
    project_id: str = "default",
    limit: int = 100,
    _auth: None = Depends(require_viewer_api_key),
):
    return MemoryConsolidator(database).list_capsules(
        project_id=project_id, limit=limit
    )


@app.post("/retention/redact")
def retention_redact(
    req: RedactEvidenceRequest, _auth: None = Depends(require_admin_api_key)
):
    return RetentionManager(database).redact_evidence(
        req.evidence_id, actor=req.actor, reason=req.reason
    )


@app.get("/retention/history")
def retention_history(
    project_id: str = "default",
    limit: int = 100,
    _auth: None = Depends(require_viewer_api_key),
):
    return RetentionManager(database).history(
        project_id=project_id,
        limit=limit,
    )


@app.post("/maintenance/rebuild-fts")
def maintenance_rebuild_fts(
    project_id: str = "default", _auth: None = Depends(require_admin_api_key)
):
    return MaintenanceManager(database).rebuild_fts(project_id=project_id)


@app.post("/maintenance/rebuild-embeddings")
def maintenance_rebuild_embeddings(
    project_id: str = "default",
    owner_type: str = "chunk",
    _auth: None = Depends(require_admin_api_key),
):
    return MaintenanceManager(database).rebuild_embeddings(
        project_id=project_id, owner_type=owner_type
    )


@app.post("/runtime/migrate")
def runtime_migrate(_auth: None = Depends(require_admin_api_key)):
    from .migrations import MigrationManager

    return MigrationManager(database).apply_all()


@app.post("/ingest/governed")
def ingest_governed(
    req: GovernedIngestRequest, _auth: None = Depends(require_editor_api_key)
):
    extractor_mode = req.extractor_mode or settings.extractor_mode
    extractor_provider = req.extractor_provider or settings.extractor_provider
    extractor_schema_version = (
        req.extractor_schema_version or settings.extractor_schema_version
    )
    strict_provider_invalid = extractor_mode == "json_strict" and (
        not isinstance(extractor_provider, str)
        or not extractor_provider.strip()
        or build_default_registry().get(extractor_provider) is None
    )
    if (
        strict_provider_invalid
        and not req.allow_evidence_only_on_extractor_failure
    ):
        raise HTTPException(
            status_code=400,
            detail="structured_extractor_unavailable",
        )
    if (
        strict_provider_invalid
        and req.allow_evidence_only_on_extractor_failure
    ):
        result = TransactionalIngestionPipeline(database).ingest_text(
            req.text,
            source_type=req.source_type,
            title=req.title,
            source_uri=req.source_uri,
            project_id=req.project_id,
            actor=req.actor,
            extract_claims=False,
            extractor_mode=extractor_mode,
            extractor_provider=extractor_provider,
            extractor_schema_version=extractor_schema_version,
        )
        result["extractor_outcome"] = "strict_rejected"
        result["reason"] = "structured_extractor_unavailable"
        return result
    return TransactionalIngestionPipeline(database).ingest_text(
        req.text,
        source_type=req.source_type,
        title=req.title,
        source_uri=req.source_uri,
        project_id=req.project_id,
        actor=req.actor,
        extract_claims=req.extract_claims,
        extractor_mode=extractor_mode,
        extractor_provider=extractor_provider,
        extractor_schema_version=extractor_schema_version,
    )


@app.get("/ledger")
def ledger_list(
    project_id: str = "default",
    limit: int = 100,
    _auth: None = Depends(require_viewer_api_key),
):
    return MemoryLedger(database).list(project_id=project_id, limit=limit)


@app.get("/ledger/verify")
def ledger_verify(_auth: None = Depends(require_viewer_api_key)):
    return MemoryLedger(database).verify_chain()


@app.post("/claims/clusters/rebuild")
def claim_clusters_rebuild(
    project_id: str = "default",
    min_claims: int = 1,
    _auth: None = Depends(require_editor_api_key),
):
    return ClaimCanonicalizer(database).rebuild_clusters(
        project_id=project_id, min_claims=min_claims
    )


@app.get("/claims/clusters")
def claim_clusters(
    project_id: str = "default",
    limit: int = 100,
    _auth: None = Depends(require_viewer_api_key),
):
    return ClaimCanonicalizer(database).list_clusters(
        project_id=project_id, limit=limit
    )


@app.post("/eval/cases")
def eval_add_case(
    req: EvalCaseRequest,
    _auth: None = Depends(require_editor_api_key),
):
    return RetrievalEvalSuite(database).add_case(
        query=req.query,
        expected_claim_ids=req.expected_claim_ids,
        expected_terms=req.expected_terms,
        project_id=req.project_id,
    )


@app.post("/eval/suite")
def eval_suite(
    project_id: str = "default",
    top_k: int = 10,
    _auth: None = Depends(require_editor_api_key),
):
    return RetrievalEvalSuite(database).run(project_id=project_id, top_k=top_k)
