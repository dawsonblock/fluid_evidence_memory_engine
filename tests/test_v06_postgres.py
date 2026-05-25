from feme.migrations import (
    V07_POSTGRES_NATIVE_FTS_SQL,
    V08_POSTGRES_LEDGER_IMMUTABLE_SQL,
    V09_EVIDENCE_DEDUP_INDEX_SQL,
    V13_EXTRACTOR_AUDIT_SQL,
)
from feme.postgres_db import (
    PostgresDatabase,
    convert_qmark_placeholders,
    rewrite_sql_for_postgres,
    split_sql_script,
)
from feme.runtime import make_database


def test_qmark_translation_skips_string_literals():
    sql = "SELECT '?' AS literal, id FROM memory_claims WHERE project_id = ? AND title = 'what?'"
    assert (
        convert_qmark_placeholders(sql)
        == "SELECT '?' AS literal, id FROM memory_claims WHERE project_id = %s AND title = 'what?'"
    )


def test_insert_or_ignore_translation():
    sql = "INSERT OR IGNORE INTO projects (id, name) VALUES (?, ?)"
    out = rewrite_sql_for_postgres(sql)
    assert (
        out == "INSERT INTO projects (id, name) VALUES (%s, %s) ON CONFLICT DO NOTHING"
    )


def test_schema_meta_replace_translation():
    sql = "INSERT OR REPLACE INTO schema_meta (key, value, updated_at) VALUES (?, ?, ?)"
    out = rewrite_sql_for_postgres(sql)
    assert out and out.startswith("INSERT INTO schema_meta")
    assert "ON CONFLICT (key) DO UPDATE" in out
    assert "%s" in out


def test_scalar_min_translation_to_least():
    sql = "UPDATE memory_claims SET salience = MIN(1.0, salience + ?) WHERE id = ?"
    out = rewrite_sql_for_postgres(sql)
    assert (
        out
        == "UPDATE memory_claims SET salience = LEAST(1.0, salience + %s) WHERE id = %s"
    )


def test_group_concat_translation_to_string_agg():
    sql = "SELECT GROUP_CONCAT(id) AS ids FROM evidence_sources WHERE project_id = ?"
    out = rewrite_sql_for_postgres(sql)
    assert (
        out
        == "SELECT string_agg((id)::text, ',') AS ids FROM evidence_sources WHERE project_id = %s"
    )


def test_split_sql_script_handles_semicolon_in_string():
    script = "CREATE TABLE x (id text); INSERT INTO x VALUES ('a;b');"
    parts = split_sql_script(script)
    assert len(parts) == 2
    assert "'a;b'" in parts[1]


def test_make_database_selects_postgres_by_dsn():
    db = make_database("postgresql://user:pass@localhost:5432/feme")
    assert isinstance(db, PostgresDatabase)
    assert db.backend == "postgres"
    assert "pass" not in db.path


def test_v07_postgres_native_fts_migration_sql_contains_expected_artifacts():
    assert "ADD COLUMN IF NOT EXISTS claim_tsv" in V07_POSTGRES_NATIVE_FTS_SQL
    assert "ADD COLUMN IF NOT EXISTS chunk_tsv" in V07_POSTGRES_NATIVE_FTS_SQL
    assert "USING GIN (claim_tsv)" in V07_POSTGRES_NATIVE_FTS_SQL
    assert "USING GIN (chunk_tsv)" in V07_POSTGRES_NATIVE_FTS_SQL


def test_v08_postgres_ledger_immutable_migration_sql_contains_expected_artifacts():
    assert "feme_memory_ledger_block_mutation" in V08_POSTGRES_LEDGER_IMMUTABLE_SQL
    assert (
        "DROP TRIGGER IF EXISTS trg_memory_ledger_block_mutation"
        in V08_POSTGRES_LEDGER_IMMUTABLE_SQL
    )
    assert (
        "BEFORE UPDATE OR DELETE ON memory_ledger" in V08_POSTGRES_LEDGER_IMMUTABLE_SQL
    )


def test_split_sql_script_preserves_plpgsql_function_body_as_one_statement():
    parts = split_sql_script(V08_POSTGRES_LEDGER_IMMUTABLE_SQL)
    assert len(parts) == 3
    assert parts[0].startswith(
        "CREATE OR REPLACE FUNCTION feme_memory_ledger_block_mutation()"
    )
    assert "RAISE EXCEPTION 'memory_ledger is append-only';" in parts[0]
    assert parts[1].startswith(
        "DROP TRIGGER IF EXISTS trg_memory_ledger_block_mutation ON memory_ledger"
    )
    assert parts[2].startswith("CREATE TRIGGER trg_memory_ledger_block_mutation")


def test_v09_evidence_dedup_unique_index_sql_contains_expected_artifacts():
    assert (
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_evidence_project_sha_unique"
        in V09_EVIDENCE_DEDUP_INDEX_SQL
    )
    assert "evidence_sources(project_id, sha256)" in V09_EVIDENCE_DEDUP_INDEX_SQL


def test_v13_extractor_audit_sql_contains_expected_artifacts():
    assert "CREATE TABLE IF NOT EXISTS extractor_audit" in V13_EXTRACTOR_AUDIT_SQL
    assert "extractor_mode TEXT NOT NULL" in V13_EXTRACTOR_AUDIT_SQL
    assert "extractor_provider TEXT NOT NULL" in V13_EXTRACTOR_AUDIT_SQL
    assert "idx_extractor_audit_evidence" in V13_EXTRACTOR_AUDIT_SQL
