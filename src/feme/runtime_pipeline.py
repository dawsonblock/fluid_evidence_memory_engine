from __future__ import annotations

from .claim_canonicalizer import ClaimCanonicalizer
from .claim_extractor import extract_candidates_for_evidence
from .contradiction import ContradictionEngine
from .db import Database
from .evidence import EvidenceIngestor
from .ledger import MemoryLedger
from .projects import ProjectManager
from .utils import json_dumps, new_id, now_iso
from .write_governor import MemoryWriteGovernor


class TransactionalIngestionPipeline:
    """Governed ingestion path with job status, ledger events, and rollback markers.

    The lower EvidenceIngestor remains usable for quick local workflows. This
    pipeline is the preferred v0.5 route when a project needs auditable runtime
    behavior.
    """

    def __init__(self, db: Database):
        self.db = db
        self.ledger = MemoryLedger(db)

    def ingest_text(
        self,
        text: str,
        *,
        source_type: str = "note",
        title: str | None = None,
        source_uri: str | None = None,
        project_id: str = "default",
        actor: str | None = None,
        extract_claims: bool = True,
        rebuild_clusters: bool = True,
        extractor_mode: str = "json_with_fallback",
        extractor_provider: str | None = None,
    ) -> dict:
        ProjectManager(self.db).ensure(project_id)
        run_id = new_id("run")
        now = now_iso()
        try:
            with self.db.connect() as con:
                con.execute(
                    """
                    INSERT INTO ingestion_jobs
                    (id, project_id, source_type, source_uri, status, started_at, metadata_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        project_id,
                        source_type,
                        source_uri,
                        "pipeline_started",
                        now,
                        json_dumps({"title": title, "actor": actor}),
                    ),
                )
                self.ledger.append(
                    event_type="ingestion_started",
                    object_type="ingestion_run",
                    object_id=run_id,
                    project_id=project_id,
                    actor=actor,
                    after={
                        "source_type": source_type,
                        "title": title,
                        "source_uri": source_uri,
                    },
                    con=con,
                    autocommit=False,
                )

                ingest_result = EvidenceIngestor(self.db).ingest_text(
                    text,
                    source_type=source_type,
                    title=title,
                    source_uri=source_uri,
                    project_id=project_id,
                    con=con,
                    autocommit=False,
                )
                evidence_id = ingest_result["evidence_id"]
                self.ledger.append(
                    event_type="evidence_ingested",
                    object_type="evidence",
                    object_id=evidence_id,
                    project_id=project_id,
                    actor=actor,
                    after=ingest_result,
                    con=con,
                    autocommit=False,
                )

                writes = []
                contradictions = []
                if extract_claims and not ingest_result.get("duplicate"):
                    governor = MemoryWriteGovernor(self.db)
                    contradiction_engine = ContradictionEngine(self.db)
                    candidates = extract_candidates_for_evidence(
                        self.db,
                        evidence_id,
                        extractor_mode=extractor_mode,
                        extractor_provider=extractor_provider,
                        con=con,
                    )
                    for candidate in candidates:
                        write = governor.commit_candidate(
                            candidate, project_id=project_id, con=con, autocommit=False
                        )
                        writes.append(write.model_dump())
                        if write.matched_claim_id:
                            self.ledger.append(
                                event_type="claim_written",
                                object_type="claim",
                                object_id=write.matched_claim_id,
                                project_id=project_id,
                                actor=actor,
                                after=write.model_dump(),
                                reason="candidate passed memory write governor",
                                con=con,
                                autocommit=False,
                            )
                            contradictions.extend(
                                contradiction_engine.scan_new_claim(
                                    write.matched_claim_id, con=con, autocommit=False
                                )
                            )

                clusters = {"clusters_created_or_updated": 0}
                if rebuild_clusters:
                    clusters = ClaimCanonicalizer(self.db).rebuild_clusters(
                        project_id=project_id, con=con, autocommit=False
                    )
                    self.ledger.append(
                        event_type="clusters_rebuilt",
                        object_type="claim_clusters",
                        object_id=project_id,
                        project_id=project_id,
                        actor=actor,
                        after=clusters,
                        con=con,
                        autocommit=False,
                    )

                con.execute(
                    "UPDATE ingestion_jobs SET status = ?, evidence_id = ?, finished_at = ? WHERE id = ?",
                    ("pipeline_finished", evidence_id, now_iso(), run_id),
                )
                self.ledger.append(
                    event_type="ingestion_finished",
                    object_type="ingestion_run",
                    object_id=run_id,
                    project_id=project_id,
                    actor=actor,
                    after={
                        "evidence_id": evidence_id,
                        "write_count": len(writes),
                        "contradiction_count": len(contradictions),
                        **clusters,
                    },
                    con=con,
                    autocommit=False,
                )
                con.commit()

            return {
                "run_id": run_id,
                "evidence_id": evidence_id,
                "duplicate": ingest_result.get("duplicate", False),
                "entity_mention_ids": ingest_result.get("entity_mention_ids", []),
                "timeline_event_ids": ingest_result.get("timeline_event_ids", []),
                "claim_writes": writes,
                "contradictions": contradictions,
                "clusters": clusters,
            }
        except Exception as exc:
            with self.db.connect() as con:
                row = con.execute(
                    "SELECT id FROM ingestion_jobs WHERE id = ?", (run_id,)
                ).fetchone()
                if row:
                    con.execute(
                        "UPDATE ingestion_jobs SET status = ?, error = ?, finished_at = ? WHERE id = ?",
                        ("pipeline_failed", str(exc), now_iso(), run_id),
                    )
                else:
                    con.execute(
                        """
                        INSERT INTO ingestion_jobs
                        (id, project_id, source_type, source_uri, status, started_at, finished_at, error, metadata_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            run_id,
                            project_id,
                            source_type,
                            source_uri,
                            "pipeline_failed",
                            now,
                            now_iso(),
                            str(exc),
                            json_dumps({"title": title, "actor": actor}),
                        ),
                    )
                con.commit()
            self.ledger.append(
                event_type="ingestion_failed",
                object_type="ingestion_run",
                object_id=run_id,
                project_id=project_id,
                actor=actor,
                after={"error": str(exc)},
            )
            raise
