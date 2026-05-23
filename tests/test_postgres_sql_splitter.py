from feme.migrations import V08_POSTGRES_LEDGER_IMMUTABLE_SQL
from feme.postgres_db import split_sql_script


def test_split_sql_script_preserves_dollar_quoted_function():
    statements = split_sql_script(V08_POSTGRES_LEDGER_IMMUTABLE_SQL)
    assert len(statements) == 3
    assert statements[0].startswith("CREATE OR REPLACE FUNCTION")
    assert "$$" in statements[0]
    assert "END;" in statements[0]
    assert statements[1].startswith("DROP TRIGGER")
    assert statements[2].startswith("CREATE TRIGGER")


def test_split_sql_script_supports_tagged_dollar_quotes():
    sql = """
    CREATE FUNCTION x() RETURNS trigger AS $func$
    BEGIN
      RAISE EXCEPTION 'no; split';
    END;
    $func$ LANGUAGE plpgsql;
    SELECT 1;
    """
    statements = split_sql_script(sql)
    assert len(statements) == 2
    assert "RAISE EXCEPTION" in statements[0]
    assert statements[1] == "SELECT 1"


def test_split_sql_script_ignores_semicolon_inside_string():
    sql = "INSERT INTO x VALUES ('a;b'); SELECT 1;"
    statements = split_sql_script(sql)
    assert len(statements) == 2
