from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from .claim_extractor import extract_candidates_for_evidence
from .config import get_settings
from .context_builder import ContextBuilder
from .contradiction import ContradictionEngine
from .db import Database
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
from .migrations import MigrationManager
from .claim_canonicalizer import ClaimCanonicalizer
from .retrieval_eval_suite import RetrievalEvalSuite
from .runtime import make_database, runtime_health

app = FastAPI(title="Fluid Evidence Memory Engine", version="0.7.0")
settings = get_settings()
database = make_database()
database.init()


class IngestRequest(BaseModel):
    text: str
    source_type: str = "note"
    title: str | None = None
    project_id: str = "default"
    extract_claims: bool = True
    extract_entities: bool = True


class SearchRequest(BaseModel):
    query: str
    project_id: str = "default"
    top_k: int = 10


class ContextRequest(BaseModel):
    question: str
    project_id: str = "default"
    token_budget: int = 12000


class ReviewActionRequest(BaseModel):
    claim_id: str
    action: str
    reviewer: str | None = None
    reason: str = ""


class VerifyAnswerRequest(BaseModel):
    question: str
    answer_text: str | None = None
    project_id: str = "default"
    token_budget: int = 12000


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


class EvalCaseRequest(BaseModel):
    query: str
    project_id: str = "default"
    expected_claim_ids: list[str] = []
    expected_terms: list[str] = []


@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": "0.7.0",
        "db_backend": settings.db_backend,
        "db_path": getattr(database, "path", settings.db_path),
        "runtime": runtime_health(database),
    }


@app.post("/ingest")
def ingest(req: IngestRequest):
    result = EvidenceIngestor(database).ingest_text(
        req.text,
        source_type=req.source_type,
        title=req.title,
        project_id=req.project_id,
        extract_entities=req.extract_entities,
    )
    claim_results = []
    contradictions = []
    if req.extract_claims:
        governor = MemoryWriteGovernor(database)
        contradiction = ContradictionEngine(database)
        candidates = extract_candidates_for_evidence(database, result["evidence_id"])
        for candidate in candidates:
            write = governor.commit_candidate(candidate, project_id=req.project_id)
            if write.matched_claim_id:
                contradictions.extend(
                    contradiction.scan_new_claim(write.matched_claim_id)
                )
            claim_results.append(write.model_dump())
    return {
        "evidence": result,
        "claim_writes": claim_results,
        "contradictions": contradictions,
    }


@app.post("/search")
def search(req: SearchRequest):
    return [
        r.model_dump()
        for r in RetrievalPlanner(database).search(
            req.query, project_id=req.project_id, top_k=req.top_k
        )
    ]


@app.post("/context")
def context(req: ContextRequest):
    return (
        ContextBuilder(database)
        .build(req.question, project_id=req.project_id, token_budget=req.token_budget)
        .model_dump()
    )


@app.post("/verify")
def verify(req: VerifyAnswerRequest):
    packet = ContextBuilder(database).build(
        req.question, project_id=req.project_id, token_budget=req.token_budget
    )
    verifier = AnswerVerifier(database)
    if req.answer_text:
        return verifier.verify_answer_text(packet, req.answer_text).model_dump()
    return verifier.verify_context(packet).model_dump()


@app.post("/lifecycle/decay")
def lifecycle_decay(project_id: str = "default"):
    return MemoryLifecycleManager(database).run_decay(project_id=project_id)


@app.get("/claims")
def claims(project_id: str = "default", limit: int = 50):
    with database.connect() as con:
        rows = con.execute(
            "SELECT * FROM memory_claims WHERE project_id = ? ORDER BY created_at DESC LIMIT ?",
            (project_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


@app.get("/entities")
def entities(limit: int = 100):
    with database.connect() as con:
        rows = con.execute(
            "SELECT e.*, COUNT(m.id) AS mention_count FROM entities e LEFT JOIN entity_mentions m ON m.entity_id = e.id GROUP BY e.id ORDER BY mention_count DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


@app.post("/export")
def export(project_id: str = "default", out_path: str = "feme_export.json"):
    return ProjectExporter(database).export_project(project_id, out_path)


@app.get("/projects")
def list_projects():
    return ProjectManager(database).list()


@app.get("/projects/{project_id}/stats")
def project_stats(project_id: str):
    return ProjectManager(database).stats(project_id)


@app.get("/review/pending")
def review_pending(project_id: str = "default", limit: int = 50):
    return ReviewQueue(database).list_pending(project_id=project_id, limit=limit)


@app.post("/review/action")
def review_action(req: ReviewActionRequest):
    return ReviewQueue(database).act(
        req.claim_id, req.action, reviewer=req.reviewer, reason=req.reason
    )


@app.get("/claims/{claim_id}/trace")
def claim_trace(claim_id: str):
    return ProvenanceGraph(database).trace_claim(claim_id)


@app.post("/integrity/check")
def integrity_check(project_id: str = "default"):
    return IntegrityChecker(database).run(project_id=project_id)


@app.post("/backup")
def backup(out_path: str = "feme_backup.sqlite"):
    return BackupManager(database).backup(out_path)


@app.get("/sources")
def source_list(project_id: str = "default"):
    SourceRegistry(database).ensure_defaults(project_id=project_id)
    return SourceRegistry(database).list(project_id=project_id)


@app.post("/sources")
def source_set(req: SourceSetRequest):
    return SourceRegistry(database).upsert(
        req.source_type,
        project_id=req.project_id,
        enabled=req.enabled,
        default_quality=req.default_quality,
        review_required=req.review_required,
    )


@app.post("/timeline/rebuild")
def timeline_rebuild(project_id: str = "default"):
    return TimelineManager(database).rebuild_project(project_id=project_id)


@app.get("/timeline")
def timeline(project_id: str = "default", limit: int = 100):
    return TimelineManager(database).list(project_id=project_id, limit=limit)


@app.post("/citations")
def citations(req: ContextRequest, persist: bool = False):
    packet = ContextBuilder(database).build(
        req.question, project_id=req.project_id, token_budget=req.token_budget
    )
    return CitationManager(database).citations_for_context(packet, persist=persist)


@app.post("/answer/scaffold")
def answer_scaffold(req: ContextRequest):
    return GroundedAnswerBuilder(database).build_scaffold(
        req.question, project_id=req.project_id, token_budget=req.token_budget
    )


@app.post("/consolidate")
def consolidate(project_id: str = "default"):
    manager = MemoryConsolidator(database)
    result = manager.create_subject_capsules(project_id=project_id)
    result.update(manager.link_near_duplicate_claims(project_id=project_id))
    return result


@app.get("/capsules")
def capsules(project_id: str = "default", limit: int = 100):
    return MemoryConsolidator(database).list_capsules(
        project_id=project_id, limit=limit
    )


@app.post("/retention/redact")
def retention_redact(req: RedactEvidenceRequest):
    return RetentionManager(database).redact_evidence(
        req.evidence_id, actor=req.actor, reason=req.reason
    )


@app.get("/retention/history")
def retention_history(project_id: str = "default", limit: int = 100):
    return RetentionManager(database).history(project_id=project_id, limit=limit)


@app.post("/maintenance/rebuild-fts")
def maintenance_rebuild_fts(project_id: str = "default"):
    return MaintenanceManager(database).rebuild_fts(project_id=project_id)


@app.post("/maintenance/rebuild-embeddings")
def maintenance_rebuild_embeddings(
    project_id: str = "default", owner_type: str = "chunk"
):
    return MaintenanceManager(database).rebuild_embeddings(
        project_id=project_id, owner_type=owner_type
    )


@app.post("/runtime/migrate")
def runtime_migrate():
    return MigrationManager(database).apply_all()


@app.post("/ingest/governed")
def ingest_governed(req: GovernedIngestRequest):
    return TransactionalIngestionPipeline(database).ingest_text(
        req.text,
        source_type=req.source_type,
        title=req.title,
        source_uri=req.source_uri,
        project_id=req.project_id,
        actor=req.actor,
        extract_claims=req.extract_claims,
    )


@app.get("/ledger")
def ledger_list(project_id: str = "default", limit: int = 100):
    return MemoryLedger(database).list(project_id=project_id, limit=limit)


@app.get("/ledger/verify")
def ledger_verify():
    return MemoryLedger(database).verify_chain()


@app.post("/claims/clusters/rebuild")
def claim_clusters_rebuild(project_id: str = "default", min_claims: int = 1):
    return ClaimCanonicalizer(database).rebuild_clusters(
        project_id=project_id, min_claims=min_claims
    )


@app.get("/claims/clusters")
def claim_clusters(project_id: str = "default", limit: int = 100):
    return ClaimCanonicalizer(database).list_clusters(
        project_id=project_id, limit=limit
    )


@app.post("/eval/cases")
def eval_add_case(req: EvalCaseRequest):
    return RetrievalEvalSuite(database).add_case(
        query=req.query,
        expected_claim_ids=req.expected_claim_ids,
        expected_terms=req.expected_terms,
        project_id=req.project_id,
    )


@app.post("/eval/suite")
def eval_suite(project_id: str = "default", top_k: int = 10):
    return RetrievalEvalSuite(database).run(project_id=project_id, top_k=top_k)
