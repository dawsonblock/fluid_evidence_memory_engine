from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from .utils import now_iso

ROOT_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "sql" / "postgres_schema.sql"
PACKAGE_SCHEMA_PATH = Path(__file__).resolve().parent / "postgres_schema.sql"
POSTGRES_SCHEMA_VERSION = "0.7.2"


class PostgresDependencyError(RuntimeError):
    pass


class PostgresDatabase:
    """PostgreSQL database facade compatible with FEME's SQLite-style modules.

    FEME's earlier modules call `con.execute(sql, params)` with SQLite `?`
    placeholders and expect mapping-like rows. This class provides a thin
    compatibility layer over psycopg so the same governed ingestion/retrieval
    paths can run against PostgreSQL while the codebase is being migrated toward
    the backend-neutral `MemoryStore` interface.
    """

    backend = "postgres"

    def __init__(self, dsn: str):
        self.dsn = dsn
        self.path = _redact_dsn(dsn)

    def connect(self) -> "PostgresConnection":
        try:
            import psycopg  # type: ignore
            from psycopg.rows import dict_row  # type: ignore
        except ImportError as exc:
            raise PostgresDependencyError(
                "PostgreSQL backend requires psycopg. Install with: "
                "pip install 'fluid-evidence-memory-engine[postgres]'"
            ) from exc
        con = psycopg.connect(self.dsn, row_factory=dict_row)
        return PostgresConnection(con)

    def init(self) -> None:
        schema_path = (
            ROOT_SCHEMA_PATH if ROOT_SCHEMA_PATH.exists() else PACKAGE_SCHEMA_PATH
        )
        schema = schema_path.read_text(encoding="utf-8")
        with self.connect() as con:
            con.executescript(schema)
            now = now_iso()
            con.execute(
                """
                INSERT INTO schema_meta (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT (key) DO UPDATE
                SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at
                """,
                ("schema_version", POSTGRES_SCHEMA_VERSION, now),
            )
            con.execute(
                """
                INSERT INTO projects (id, name, description, created_at, updated_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO NOTHING
                """,
                ("default", "default", "Default project", now, now, "{}"),
            )
            con.commit()
        try:
            from .source_registry import SourceRegistry

            SourceRegistry(self).ensure_defaults(project_id="default")
        except Exception:
            # Keep init deterministic even if defaults fail; runtime-health and
            # integrity checks expose registry issues.
            pass

    def schema_version(self) -> str | None:
        try:
            with self.connect() as con:
                row = con.execute(
                    "SELECT value FROM schema_meta WHERE key = ?", ("schema_version",)
                ).fetchone()
            return row["value"] if row else None
        except Exception:
            return None


class PostgresConnection:
    def __init__(self, raw_connection: Any):
        self._con = raw_connection

    def __enter__(self) -> "PostgresConnection":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        try:
            if exc_type is None:
                self._con.commit()
            else:
                self._con.rollback()
        finally:
            self._con.close()

    def execute(
        self, sql: str, params: Iterable[Any] | None = None
    ) -> "PostgresCursor":
        rewritten = rewrite_sql_for_postgres(sql)
        if rewritten is None:
            return EmptyCursor()
        cur = self._con.cursor()
        cur.execute(rewritten, tuple(params or ()))
        return PostgresCursor(cur)

    def executescript(self, script: str) -> None:
        for statement in split_sql_script(script):
            rewritten = rewrite_sql_for_postgres(statement)
            if rewritten is None:
                continue
            cur = self._con.cursor()
            cur.execute(rewritten)
            cur.close()

    def commit(self) -> None:
        self._con.commit()

    def rollback(self) -> None:
        self._con.rollback()

    def close(self) -> None:
        self._con.close()


class PostgresCursor:
    def __init__(self, cursor: Any):
        self._cursor = cursor

    def __iter__(self):
        return iter(self._cursor)

    @property
    def rowcount(self) -> int:
        return int(self._cursor.rowcount or 0)

    @property
    def description(self) -> Any:
        return self._cursor.description

    def fetchone(self) -> dict[str, Any] | None:
        return self._cursor.fetchone()

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._cursor.fetchall())


class EmptyCursor:
    rowcount = 0
    description = None

    def __iter__(self):
        return iter(())

    def fetchone(self) -> None:
        return None

    def fetchall(self) -> list[dict[str, Any]]:
        return []


def rewrite_sql_for_postgres(sql: str) -> str | None:
    """Translate the SQLite subset used by FEME into PostgreSQL SQL.

    This is intentionally conservative. It is not a general SQL transpiler; it
    only covers the syntax FEME emits: qmark placeholders, INSERT OR IGNORE,
    INSERT OR REPLACE for schema_meta, SQLite PRAGMAs, and scalar MIN used as
    LEAST for salience updates.
    """

    stripped = sql.strip()
    if not stripped:
        return None
    upper = stripped.upper()
    if upper.startswith("PRAGMA "):
        return None
    if "CREATE VIRTUAL TABLE" in upper:
        return None

    out = stripped.rstrip(";")

    if re.match(r"^INSERT\s+OR\s+REPLACE\s+INTO\s+schema_meta\b", out, flags=re.I):
        out = re.sub(r"^INSERT\s+OR\s+REPLACE\s+INTO", "INSERT INTO", out, flags=re.I)
        if "ON CONFLICT" not in out.upper():
            out += " ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at"
    elif re.match(r"^INSERT\s+OR\s+IGNORE\s+INTO\b", out, flags=re.I):
        out = re.sub(r"^INSERT\s+OR\s+IGNORE\s+INTO", "INSERT INTO", out, flags=re.I)
        if "ON CONFLICT" not in out.upper():
            out += " ON CONFLICT DO NOTHING"

    out = re.sub(
        r"GROUP_CONCAT\(\s*([^)]+?)\s*\)",
        r"string_agg((\1)::text, ',')",
        out,
        flags=re.I,
    )
    out = re.sub(r"\bMIN\(\s*1\.0\s*,", "LEAST(1.0,", out, flags=re.I)
    out = convert_qmark_placeholders(out)
    return out


def convert_qmark_placeholders(sql: str) -> str:
    out: list[str] = []
    in_single = False
    in_double = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        if ch == "'" and not in_double:
            out.append(ch)
            if in_single and i + 1 < len(sql) and sql[i + 1] == "'":
                out.append(sql[i + 1])
                i += 2
                continue
            in_single = not in_single
        elif ch == '"' and not in_single:
            out.append(ch)
            in_double = not in_double
        elif ch == "?" and not in_single and not in_double:
            out.append("%s")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def split_sql_script(script: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_single = False
    in_double = False
    dollar_tag: str | None = None
    line_comment = False
    block_comment = False
    i = 0
    while i < len(script):
        ch = script[i]
        nxt = script[i + 1] if i + 1 < len(script) else ""
        if dollar_tag is not None:
            if script.startswith(dollar_tag, i):
                current.extend(dollar_tag)
                i += len(dollar_tag)
                dollar_tag = None
                continue
            current.append(ch)
            i += 1
            continue
        if line_comment:
            current.append(ch)
            if ch == "\n":
                line_comment = False
            i += 1
            continue
        if block_comment:
            current.append(ch)
            if ch == "*" and nxt == "/":
                current.append(nxt)
                block_comment = False
                i += 2
            else:
                i += 1
            continue
        if not in_single and not in_double and ch == "-" and nxt == "-":
            current.append(ch)
            current.append(nxt)
            line_comment = True
            i += 2
            continue
        if not in_single and not in_double and ch == "/" and nxt == "*":
            current.append(ch)
            current.append(nxt)
            block_comment = True
            i += 2
            continue
        if ch == "'" and not in_double:
            current.append(ch)
            if in_single and nxt == "'":
                current.append(nxt)
                i += 2
                continue
            in_single = not in_single
        elif ch == '"' and not in_single:
            current.append(ch)
            in_double = not in_double
        elif not in_single and not in_double and ch == "$":
            j = i + 1
            while j < len(script) and (script[j].isalnum() or script[j] == "_"):
                j += 1
            if j < len(script) and script[j] == "$":
                dollar_tag = script[i : j + 1]
                current.extend(dollar_tag)
                i = j + 1
                continue
            current.append(ch)
        elif ch == ";" and not in_single and not in_double:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
        else:
            current.append(ch)
        i += 1
    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def _redact_dsn(dsn: str) -> str:
    if "://" not in dsn:
        return "postgres://***"
    prefix, rest = dsn.split("://", 1)
    if "@" not in rest:
        return f"{prefix}://***"
    host = rest.split("@", 1)[-1]
    return f"{prefix}://***@{host}"
