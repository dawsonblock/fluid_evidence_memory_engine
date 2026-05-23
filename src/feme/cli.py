from __future__ import annotations

import json
from pathlib import Path

import typer
from rich import print
from rich.table import Table

from .audit import AuditReader
from .claim_extractor import extract_candidates_for_evidence
from .config import get_settings
from .context_builder import ContextBuilder
from .contradiction import ContradictionEngine
from .db import Database
from .evidence import EvidenceIngestor
from .evaluation import RetrievalEvaluator
from .eval import evaluate_extraction_fixture
from .export_import import ProjectExporter
from .lifecycle import MemoryLifecycleManager
from .models import EvaluationCase
from .retrieval import RetrievalPlanner
from .verifier import AnswerVerifier
from .write_governor import MemoryWriteGovernor
from .projects import ProjectManager
from .review import ReviewQueue
from .provenance import ProvenanceGraph
from .integrity import IntegrityChecker
from .backup import BackupManager
from .source_registry import SourceRegistry
from .temporal import TimelineManager
from .citations import CitationManager
from .consolidation import MemoryConsolidator
from .retention import RetentionManager
from .maintenance import MaintenanceManager
from .answer_builder import GroundedAnswerBuilder
from .migrations import MigrationManager
from .ledger import MemoryLedger
from .runtime_pipeline import TransactionalIngestionPipeline
from .claim_canonicalizer import ClaimCanonicalizer
from .retrieval_eval_suite import RetrievalEvalSuite
from .runtime import make_database, runtime_health

app = typer.Typer(help="Fluid Evidence Memory Engine CLI")


def _db(path: str | None):
    return make_database(path)


@app.command()
def init(db: str = typer.Option(None, help="SQLite DB path or PostgreSQL DSN")):
    database = _db(db)
    database.init()
    print(
        f"[green]Initialized database:[/green] {getattr(database, 'path', db or get_settings().db_path)}"
    )


@app.command("ingest-text")
def ingest_text(
    db: str = typer.Option(None),
    text: str = typer.Option(None, help="Raw text to ingest"),
    path: str = typer.Option(None, help="Text file to ingest"),
    source_type: str = typer.Option("note"),
    title: str = typer.Option(None),
    project_id: str = typer.Option("default"),
    extract_claims: bool = typer.Option(True),
    extract_entities: bool = typer.Option(True),
    extractor_mode: str | None = typer.Option(
        None,
        help="Extractor mode: heuristic, json_with_fallback, or json_strict",
    ),
    extractor_provider: str | None = typer.Option(
        None,
        help="Extractor provider label written to extraction audit",
    ),
    extractor_schema_version: str | None = typer.Option(
        None,
        help="Extractor schema version (default: claim-extraction-v1)",
    ),
    vault_root: str = typer.Option(None, help="Optional raw file vault directory"),
):
    settings = get_settings()
    if not isinstance(text, str):
        text = None
    if not isinstance(path, str):
        path = None
    if not isinstance(source_type, str):
        source_type = "note"
    if not isinstance(title, str):
        title = None
    if not isinstance(project_id, str):
        project_id = "default"
    if not isinstance(vault_root, str):
        vault_root = None
    if not isinstance(extractor_mode, str):
        extractor_mode = settings.extractor_mode
    if not isinstance(extractor_provider, str):
        extractor_provider = settings.extractor_provider
    if not isinstance(extractor_schema_version, str):
        extractor_schema_version = settings.extractor_schema_version
    database = _db(db)
    database.init()
    ingestor = EvidenceIngestor(database)
    if path:
        result = ingestor.ingest_file(
            path,
            source_type=source_type,
            title=title,
            project_id=project_id,
            extract_entities=extract_entities,
            vault_root=vault_root,
        )
    elif text:
        result = ingestor.ingest_text(
            text,
            source_type=source_type,
            title=title,
            project_id=project_id,
            extract_entities=extract_entities,
        )
    else:
        raise typer.BadParameter("Provide --text or --path")
    print(json.dumps(result, indent=2))

    if extract_claims:
        governor = MemoryWriteGovernor(database)
        contradiction = ContradictionEngine(database)
        audit_warnings: list[str] = []
        candidates = extract_candidates_for_evidence(
            database,
            result["evidence_id"],
            extractor_mode=extractor_mode,
            extractor_provider=extractor_provider,
            extractor_schema_version=extractor_schema_version,
            require_extractor_audit=settings.require_extractor_audit,
            audit_warnings=audit_warnings,
        )
        writes = []
        contradictions = []
        for candidate in candidates:
            write = governor.commit_candidate(candidate, project_id=project_id)
            writes.append(write)
            if write.matched_claim_id:
                contradictions.extend(
                    contradiction.scan_new_claim(write.matched_claim_id)
                )
        print(f"[green]Extracted candidate claims:[/green] {len(candidates)}")
        print(
            f"[green]Durable writes:[/green] {sum(1 for w in writes if w.matched_claim_id)}"
        )
        if contradictions:
            print(f"[yellow]Contradictions detected:[/yellow] {len(contradictions)}")
        if audit_warnings:
            print(f"[yellow]Extractor audit warnings:[/yellow] {len(audit_warnings)}")


@app.command("list-claims")
def list_claims(
    db: str = typer.Option(None),
    project_id: str = typer.Option("default"),
    limit: int = 50,
):
    database = _db(db)
    with database.connect() as con:
        rows = con.execute(
            "SELECT id, subject, predicate, object, status, confidence, salience FROM memory_claims WHERE project_id = ? ORDER BY created_at DESC LIMIT ?",
            (project_id, limit),
        ).fetchall()
    columns = [
        "id",
        "subject",
        "predicate",
        "object",
        "status",
        "confidence",
        "salience",
    ]
    table = Table(title="Memory Claims")
    for col in columns:
        table.add_column(col)
    for row in rows:
        table.add_row(*(str(row[col])[:80] for col in columns))
    print(table)


@app.command("list-entities")
def list_entities(db: str = typer.Option(None), limit: int = 50):
    database = _db(db)
    with database.connect() as con:
        rows = con.execute(
            "SELECT e.entity_type, e.name, COUNT(m.id) AS mentions FROM entities e LEFT JOIN entity_mentions m ON m.entity_id = e.id GROUP BY e.id ORDER BY mentions DESC LIMIT ?",
            (limit,),
        ).fetchall()
    table = Table(title="Entities")
    for col in ["entity_type", "name", "mentions"]:
        table.add_column(col)
    for row in rows:
        table.add_row(
            str(row["entity_type"]), str(row["name"])[:80], str(row["mentions"])
        )
    print(table)


@app.command()
def search(
    db: str = typer.Option(None),
    query: str = typer.Argument(...),
    project_id: str = typer.Option("default"),
    top_k: int = 10,
    retrieval_mode: str | None = typer.Option(
        None,
        help="Retrieval mode: public (reviewed-only) or internal",
    ),
    include_pending_review: bool = typer.Option(
        False,
        "--include-pending-review/--exclude-pending-review",
        help="Whether to include claims still pending review",
    ),
):
    database = _db(db)
    if not isinstance(retrieval_mode, str):
        retrieval_mode = None
    results = RetrievalPlanner(database).search(
        query,
        project_id=project_id,
        top_k=top_k,
        retrieval_mode=retrieval_mode,
        include_pending_review=include_pending_review,
    )
    for r in results:
        print(
            f"[bold]{r.kind}[/bold] {r.id} score={r.score:.3f} spans={','.join(r.span_ids)}"
        )
        print(r.text[:600])
        print("---")


@app.command()
def context(
    db: str = typer.Option(None),
    question: str = typer.Argument(...),
    project_id: str = typer.Option("default"),
    budget: int = typer.Option(12000),
    retrieval_mode: str | None = typer.Option(
        None,
        help="Retrieval mode: public (reviewed-only) or internal",
    ),
    include_pending_review: bool = typer.Option(
        False,
        "--include-pending-review/--exclude-pending-review",
        help="Whether to include claims still pending review",
    ),
):
    database = _db(db)
    if not isinstance(retrieval_mode, str):
        retrieval_mode = None
    packet = ContextBuilder(database).build(
        question,
        project_id=project_id,
        token_budget=budget,
        retrieval_mode=retrieval_mode,
        include_pending_review=include_pending_review,
    )
    print(packet.model_dump_json(indent=2))


@app.command()
def verify(
    db: str = typer.Option(None),
    question: str = typer.Argument(...),
    answer_path: str = typer.Option(
        None, help="Optional text file containing a draft answer"
    ),
    project_id: str = typer.Option("default"),
    budget: int = typer.Option(12000),
    retrieval_mode: str | None = typer.Option(
        None,
        help="Retrieval mode: public (reviewed-only) or internal",
    ),
    include_pending_review: bool = typer.Option(
        False,
        "--include-pending-review/--exclude-pending-review",
        help="Whether to include claims still pending review",
    ),
):
    database = _db(db)
    if not isinstance(answer_path, str):
        answer_path = None
    if not isinstance(retrieval_mode, str):
        retrieval_mode = None
    if not isinstance(include_pending_review, bool):
        include_pending_review = False
    packet = ContextBuilder(database).build(
        question,
        project_id=project_id,
        token_budget=budget,
        retrieval_mode=retrieval_mode,
        include_pending_review=include_pending_review,
    )
    verifier = AnswerVerifier(database)
    if answer_path:
        answer_text = Path(answer_path).read_text(encoding="utf-8")
        report = verifier.verify_answer_text(packet, answer_text)
    else:
        report = verifier.verify_context(packet)
    typer.echo(report.model_dump_json(indent=2))


@app.command("scan-contradictions")
def scan_contradictions(db: str = typer.Option(None)):
    database = _db(db)
    engine = ContradictionEngine(database)
    with database.connect() as con:
        rows = con.execute(
            "SELECT id FROM memory_claims ORDER BY created_at DESC"
        ).fetchall()
    count = 0
    for row in rows:
        count += len(engine.scan_new_claim(row["id"]))
    print(f"[green]Contradictions detected/recorded:[/green] {count}")


@app.command("run-decay")
def run_decay(db: str = typer.Option(None), project_id: str = typer.Option("default")):
    database = _db(db)
    result = MemoryLifecycleManager(database).run_decay(project_id=project_id)
    print(json.dumps(result, indent=2))


@app.command("export-project")
def export_project(
    db: str = typer.Option(None),
    project_id: str = typer.Option("default"),
    out: str = typer.Option("feme_export.json"),
):
    database = _db(db)
    result = ProjectExporter(database).export_project(project_id, out)
    print(json.dumps(result, indent=2))


@app.command("eval-case")
def eval_case(
    db: str = typer.Option(None),
    query: str = typer.Argument(...),
    expected_term: list[str] = typer.Option(
        [], help="Expected term that should appear in retrieved text"
    ),
    project_id: str = typer.Option("default"),
    top_k: int = typer.Option(10),
):
    database = _db(db)
    case = EvaluationCase(
        id="cli_case", query=query, expected_terms=expected_term, project_id=project_id
    )
    result = RetrievalEvaluator(database).run_case(case, top_k=top_k)
    print(json.dumps(result, indent=2))


@app.command("audit")
def audit(db: str = typer.Option(None), limit: int = typer.Option(20)):
    database = _db(db)
    reader = AuditReader(database)
    print("[bold]Recent writes[/bold]")
    print(json.dumps(reader.recent_writes(limit), indent=2))
    print("[bold]Recent retrievals[/bold]")
    print(json.dumps(reader.recent_retrievals(limit), indent=2))


@app.command("project-stats")
def project_stats(
    db: str = typer.Option(None), project_id: str = typer.Option("default")
):
    database = _db(db)
    print(json.dumps(ProjectManager(database).stats(project_id), indent=2))


@app.command("review-list")
def review_list(
    db: str = typer.Option(None),
    project_id: str = typer.Option("default"),
    limit: int = typer.Option(50),
):
    database = _db(db)
    rows = ReviewQueue(database).list_pending(project_id=project_id, limit=limit)
    table = Table(title="Pending Review Claims")
    for col in ["id", "claim_text", "confidence", "source_quality", "support_count"]:
        table.add_column(col)
    for row in rows:
        table.add_row(
            str(row["id"]),
            str(row["claim_text"])[:100],
            f"{row['confidence']:.2f}",
            f"{row['source_quality']:.2f}",
            str(row["support_count"]),
        )
    print(table)


@app.command("review-action")
def review_action(
    claim_id: str = typer.Argument(...),
    action: str = typer.Argument(...),
    db: str = typer.Option(None),
    reviewer: str = typer.Option(None),
    reason: str = typer.Option(""),
):
    database = _db(db)
    print(
        json.dumps(
            ReviewQueue(database).act(
                claim_id, action, reviewer=reviewer, reason=reason
            ),
            indent=2,
        )
    )


@app.command("trace-claim")
def trace_claim(claim_id: str = typer.Argument(...), db: str = typer.Option(None)):
    database = _db(db)
    print(json.dumps(ProvenanceGraph(database).trace_claim(claim_id), indent=2))


@app.command("integrity-check")
def integrity_check(
    db: str = typer.Option(None), project_id: str = typer.Option("default")
):
    database = _db(db)
    print(json.dumps(IntegrityChecker(database).run(project_id=project_id), indent=2))


@app.command("backup-db")
def backup_db(
    db: str = typer.Option(None), out: str = typer.Option("feme_backup.sqlite")
):
    database = _db(db)
    print(json.dumps(BackupManager(database).backup(out), indent=2))


@app.command("import-project")
def import_project(
    db: str = typer.Option(None),
    path: str = typer.Argument(...),
    replace: bool = typer.Option(False),
):
    database = _db(db)
    database.init()
    print(
        json.dumps(
            ProjectExporter(database).import_project(path, replace=replace), indent=2
        )
    )


@app.command("source-list")
def source_list(
    db: str = typer.Option(None), project_id: str = typer.Option("default")
):
    database = _db(db)
    SourceRegistry(database).ensure_defaults(project_id=project_id)
    print(json.dumps(SourceRegistry(database).list(project_id=project_id), indent=2))


@app.command("source-set")
def source_set(
    source_type: str = typer.Argument(...),
    db: str = typer.Option(None),
    project_id: str = typer.Option("default"),
    enabled: bool = typer.Option(True),
    quality: float = typer.Option(None),
    review_required: bool = typer.Option(None),
):
    database = _db(db)
    print(
        json.dumps(
            SourceRegistry(database).upsert(
                source_type,
                project_id=project_id,
                enabled=enabled,
                default_quality=quality,
                review_required=review_required,
            ),
            indent=2,
        )
    )


@app.command("timeline-rebuild")
def timeline_rebuild(
    db: str = typer.Option(None), project_id: str = typer.Option("default")
):
    database = _db(db)
    print(
        json.dumps(
            TimelineManager(database).rebuild_project(project_id=project_id), indent=2
        )
    )


@app.command("timeline-list")
def timeline_list(
    db: str = typer.Option(None),
    project_id: str = typer.Option("default"),
    limit: int = typer.Option(100),
):
    database = _db(db)
    print(
        json.dumps(
            TimelineManager(database).list(project_id=project_id, limit=limit), indent=2
        )
    )


@app.command("citations")
def citations(
    db: str = typer.Option(None),
    question: str = typer.Argument(...),
    project_id: str = typer.Option("default"),
    persist: bool = typer.Option(False),
):
    database = _db(db)
    packet = ContextBuilder(database).build(question, project_id=project_id)
    print(
        json.dumps(
            CitationManager(database).citations_for_context(packet, persist=persist),
            indent=2,
        )
    )


@app.command("answer-scaffold")
def answer_scaffold(
    db: str = typer.Option(None),
    question: str = typer.Argument(...),
    project_id: str = typer.Option("default"),
    budget: int = typer.Option(12000),
):
    database = _db(db)
    print(
        json.dumps(
            GroundedAnswerBuilder(database).build_scaffold(
                question, project_id=project_id, token_budget=budget
            ),
            indent=2,
        )
    )


@app.command("consolidate")
def consolidate(
    db: str = typer.Option(None), project_id: str = typer.Option("default")
):
    database = _db(db)
    manager = MemoryConsolidator(database)
    result = manager.create_subject_capsules(project_id=project_id)
    result.update(manager.link_near_duplicate_claims(project_id=project_id))
    print(json.dumps(result, indent=2))


@app.command("capsules")
def capsules(
    db: str = typer.Option(None),
    project_id: str = typer.Option("default"),
    limit: int = typer.Option(100),
):
    database = _db(db)
    print(
        json.dumps(
            MemoryConsolidator(database).list_capsules(
                project_id=project_id, limit=limit
            ),
            indent=2,
        )
    )


@app.command("redact-evidence")
def redact_evidence(
    evidence_id: str = typer.Argument(...),
    db: str = typer.Option(None),
    actor: str = typer.Option(None),
    reason: str = typer.Option(""),
):
    database = _db(db)
    print(
        json.dumps(
            RetentionManager(database).redact_evidence(
                evidence_id, actor=actor, reason=reason
            ),
            indent=2,
        )
    )


@app.command("retention-history")
def retention_history(
    db: str = typer.Option(None),
    project_id: str = typer.Option("default"),
    limit: int = typer.Option(100),
):
    database = _db(db)
    print(
        json.dumps(
            RetentionManager(database).history(project_id=project_id, limit=limit),
            indent=2,
        )
    )


@app.command("maintenance")
def maintenance(
    db: str = typer.Option(None),
    project_id: str = typer.Option("default"),
    rebuild_fts: bool = typer.Option(False),
    rebuild_chunk_embeddings: bool = typer.Option(False),
    rebuild_claim_embeddings: bool = typer.Option(False),
    vacuum: bool = typer.Option(False),
):
    database = _db(db)
    manager = MaintenanceManager(database)
    result = {}
    if rebuild_fts:
        result["fts"] = manager.rebuild_fts(project_id=project_id)
    if rebuild_chunk_embeddings:
        result["chunk_embeddings"] = manager.rebuild_embeddings(
            project_id=project_id, owner_type="chunk"
        )
    if rebuild_claim_embeddings:
        result["claim_embeddings"] = manager.rebuild_embeddings(
            project_id=project_id, owner_type="claim"
        )
    if vacuum:
        result["vacuum"] = manager.vacuum()
    print(json.dumps(result or {"noop": True}, indent=2))


@app.command("migrate")
def migrate(db: str = typer.Option(None)):
    database = _db(db)
    database.init()
    result = MigrationManager(database).apply_all()
    result["applied_migrations"] = MigrationManager(database).list_applied()
    print(json.dumps(result, indent=2))


@app.command("runtime-health")
def runtime_health_cmd(db: str = typer.Option(None)):
    database = _db(db)
    database.init()
    print(json.dumps(runtime_health(database), indent=2))


@app.command("ingest-governed")
def ingest_governed(
    db: str = typer.Option(None),
    text: str = typer.Option(None, help="Raw text to ingest"),
    path: str = typer.Option(None, help="Text file to ingest"),
    source_type: str = typer.Option("note"),
    title: str = typer.Option(None),
    project_id: str = typer.Option("default"),
    actor: str = typer.Option(None),
    extract_claims: bool = typer.Option(True),
    extractor_mode: str | None = typer.Option(
        None,
        help="Extractor mode: heuristic, json_with_fallback, or json_strict",
    ),
    extractor_provider: str | None = typer.Option(
        None,
        help="Extractor provider label written to extraction audit",
    ),
    extractor_schema_version: str | None = typer.Option(
        None,
        help="Extractor schema version (default: claim-extraction-v1)",
    ),
):
    settings = get_settings()
    if not isinstance(text, str):
        text = None
    if not isinstance(path, str):
        path = None
    if not isinstance(source_type, str):
        source_type = "note"
    if not isinstance(title, str):
        title = None
    if not isinstance(project_id, str):
        project_id = "default"
    if not isinstance(actor, str):
        actor = None
    if not isinstance(extractor_mode, str):
        extractor_mode = settings.extractor_mode
    if not isinstance(extractor_provider, str):
        extractor_provider = settings.extractor_provider
    if not isinstance(extractor_schema_version, str):
        extractor_schema_version = settings.extractor_schema_version
    database = _db(db)
    database.init()
    if path:
        text_value = Path(path).read_text(encoding="utf-8")
        title = title or Path(path).name
    elif text:
        text_value = text
    else:
        raise typer.BadParameter("Provide --text or --path")
    result = TransactionalIngestionPipeline(database).ingest_text(
        text_value,
        source_type=source_type,
        title=title,
        project_id=project_id,
        actor=actor,
        extract_claims=extract_claims,
        extractor_mode=extractor_mode,
        extractor_provider=extractor_provider,
        extractor_schema_version=extractor_schema_version,
    )
    print(json.dumps(result, indent=2))


@app.command("ledger-list")
def ledger_list(
    db: str = typer.Option(None),
    project_id: str = typer.Option("default"),
    limit: int = typer.Option(100),
):
    database = _db(db)
    database.init()
    print(
        json.dumps(
            MemoryLedger(database).list(project_id=project_id, limit=limit), indent=2
        )
    )


@app.command("ledger-verify")
def ledger_verify(
    db: str = typer.Option(None),
    project_id: str = typer.Option("default"),
    all_projects: bool = typer.Option(
        False,
        "--all-projects",
        help="Verify hash-chain continuity across all projects",
    ),
):
    database = _db(db)
    database.init()
    selected_project = None if all_projects else project_id
    result = MemoryLedger(database).verify_chain(project_id=selected_project)
    if not all_projects and int(result.get("event_count", 0)) == 0:
        result["warning"] = (
            "No ledger events found for selected project_id. "
            "Use --all-projects to verify the full ledger."
        )
    print(json.dumps(result, indent=2))


@app.command("claim-clusters-rebuild")
def claim_clusters_rebuild(
    db: str = typer.Option(None),
    project_id: str = typer.Option("default"),
    min_claims: int = typer.Option(1),
):
    database = _db(db)
    database.init()
    print(
        json.dumps(
            ClaimCanonicalizer(database).rebuild_clusters(
                project_id=project_id, min_claims=min_claims
            ),
            indent=2,
        )
    )


@app.command("claim-clusters")
def claim_clusters(
    db: str = typer.Option(None),
    project_id: str = typer.Option("default"),
    limit: int = typer.Option(100),
):
    database = _db(db)
    database.init()
    print(
        json.dumps(
            ClaimCanonicalizer(database).list_clusters(
                project_id=project_id, limit=limit
            ),
            indent=2,
        )
    )


@app.command("eval-add-case")
def eval_add_case(
    db: str = typer.Option(None),
    query: str = typer.Argument(...),
    expected_term: list[str] = typer.Option(
        [], help="Expected term that should appear in retrieved text"
    ),
    expected_claim_id: list[str] = typer.Option([], help="Expected claim IDs"),
    project_id: str = typer.Option("default"),
):
    database = _db(db)
    database.init()
    result = RetrievalEvalSuite(database).add_case(
        query=query,
        expected_terms=expected_term,
        expected_claim_ids=expected_claim_id,
        project_id=project_id,
    )
    print(json.dumps(result, indent=2))


@app.command("eval-suite")
def eval_suite(
    db: str = typer.Option(None),
    project_id: str = typer.Option("default"),
    top_k: int = typer.Option(10),
):
    database = _db(db)
    database.init()
    print(
        json.dumps(
            RetrievalEvalSuite(database).run(project_id=project_id, top_k=top_k),
            indent=2,
        )
    )


@app.command("eval-extraction")
def eval_extraction(
    fixture: str = typer.Option(
        "tests/fixtures/extraction/project_decisions.jsonl",
        help="JSONL fixture path for extraction evaluation",
    ),
    extractor_mode: str = typer.Option(
        "heuristic",
        help="Extractor mode: heuristic, json_with_fallback, or json_strict",
    ),
    extractor_provider: str = typer.Option(
        None,
        help="Optional extractor provider for structured modes",
    ),
):
    result = evaluate_extraction_fixture(
        fixture,
        extractor_mode=extractor_mode,
        extractor_provider=extractor_provider,
    )
    print(json.dumps(result, indent=2))


@app.command("postgres-sql-smoke")
def postgres_sql_smoke():
    """Show how FEME rewrites SQLite-style runtime SQL for PostgreSQL."""
    from .postgres_db import rewrite_sql_for_postgres

    samples = [
        "SELECT * FROM memory_claims WHERE project_id = ? LIMIT ?",
        "INSERT OR IGNORE INTO projects (id, name) VALUES (?, ?)",
        "INSERT OR REPLACE INTO schema_meta (key, value, updated_at) VALUES (?, ?, ?)",
        "UPDATE memory_claims SET salience = MIN(1.0, salience + ?) WHERE id = ?",
    ]
    print(json.dumps({s: rewrite_sql_for_postgres(s) for s in samples}, indent=2))


if __name__ == "__main__":
    app()
