"""Tests for the query_tape guardrails (app/agent/sql_guard.py) and the read-only tape.

BUSINESS: the model writes SQL against the tape; these tests protect the promise
  that it can only ever read the tape: one SELECT, known columns, the loans table,
  values bound as parameters, at most 500 rows, and a database that refuses writes
  and file access even if a query got through.
TECH: pure unit tests of check_query on a small column list, plus tests that run
  against the real read-only DuckDB copy (tests/agent_fixtures.py). Each refused
  query names the attack it stands for.
"""

from __future__ import annotations

import re
from decimal import Decimal

import duckdb
import pytest

from app.agent.sql_guard import GuardrailError, check_query
from app.agent.tape_db import ReadOnlyTape
from tests.agent_fixtures import ro_tape, tape_dir  # noqa: F401  (pytest fixtures)

COLUMNS = ["loan_id", "state", "ltv", "fico", "current_upb", "note_rate", "orig_date",
           "dq_status", "mod_flag", "seller", "product"]


def guard(sql: str, max_rows: int = 500) -> object:
    """check_query with the test columns and default limits."""
    return check_query(sql, COLUMNS, max_rows=max_rows, max_chars=4000)


# =============================================================================
# Accepted queries: what a desk analyst (or a model) legitimately writes
# =============================================================================

@pytest.mark.parametrize("sql", [
    "SELECT COUNT(*) FROM loans",
    "SELECT state, COUNT(*) AS n, SUM(current_upb) FROM loans WHERE ltv > 125 GROUP BY state ORDER BY n DESC",
    "SELECT ROUND(SUM(note_rate * current_upb) / NULLIF(SUM(current_upb), 0), 3) AS wac FROM loans",
    "SELECT COUNT(*) FILTER (WHERE dq_status <> 'Current') FROM loans",
    "SELECT CASE WHEN fico < 700 THEN 'low' ELSE 'high' END AS band, AVG(fico) FROM loans GROUP BY 1",
    "SELECT EXTRACT(YEAR FROM orig_date) AS y, COUNT(*) FROM loans GROUP BY y",
    "SELECT l.fico FROM loans AS l WHERE l.ltv BETWEEN 80 AND 90 AND mod_flag = TRUE",
    "SELECT n FROM (SELECT COUNT(*) AS n FROM loans) AS t",
    "SELECT seller FROM loans WHERE seller ILIKE '%oak%' AND product LIKE '%ARM'",
    "SELECT MEDIAN(fico), MIN(orig_date), MAX(current_upb) FROM loans;",
    "select FICO from LOANS where STATE = 'NY'",
])
def test_desk_queries_are_accepted(sql: str) -> None:
    """BUSINESS: the guard must not get in the way of ordinary tape questions:
    counts, weighted averages, buckets, dates, aliases, subqueries, any case."""
    guard(sql)


def test_filter_values_become_bound_parameters() -> None:
    """BUSINESS: values never sit inside the SQL text DuckDB runs (no injection).

    TECH: 125, 'NY' and 6.5 become named parameters; each name must sit next to
      the column its value belongs to (the bug this guards against: values bound
      in the wrong order). 6.5 stays exact as Decimal. Shape constants (ROUND's 3,
      LIMIT 10) stay in the SQL.
    """
    q = guard("SELECT ROUND(AVG(fico), 3) FROM loans WHERE ltv > 125 AND state = 'NY' "
              "AND note_rate >= 6.5 LIMIT 10")
    bound = {col: q.params[name] for col, name in re.findall(r"(\w+) [<>=]+ \$(p\d+)", q.sql)}
    assert bound == {"ltv": 125, "state": "NY", "note_rate": Decimal("6.5")}
    assert "'NY'" not in q.sql and "125" not in q.sql and len(q.params) == 3
    assert "ROUND(AVG(fico), 3)" in q.sql and q.sql.endswith("LIMIT 10")


def test_in_list_values_are_bound() -> None:
    """BUSINESS: "dq_status IN ('90', 'FC')" is a filter like any other."""
    q = guard("SELECT COUNT(*) FROM loans WHERE dq_status IN ('90', 'FC')")
    assert sorted(q.params.values()) == ["90", "FC"]
    assert re.search(r"IN \(\$p\d+, \$p\d+\)", q.sql)


def test_display_sql_keeps_the_values_for_the_screen() -> None:
    """BUSINESS: the visitor reads the real query, values and all ("every answer
    shows its SQL")."""
    q = guard("SELECT COUNT(*) FROM loans WHERE state = 'NY'")
    assert "'NY'" in q.display_sql and "$p" not in q.display_sql


@pytest.mark.parametrize("sql, limit", [
    ("SELECT loan_id FROM loans", 501),
    ("SELECT loan_id FROM loans LIMIT 10", 10),
    ("SELECT loan_id FROM loans LIMIT 100000", 501),
])
def test_row_cap(sql: str, limit: int) -> None:
    """BUSINESS: no query returns more than 500 loans to the screen.

    TECH: the cap fetches max_rows + 1 to tell "exactly 500" from "more"; a smaller
      LIMIT from the model is kept.
    """
    q = guard(sql)
    assert q.fetch_limit == limit and q.sql.endswith(f"LIMIT {limit}")
    # TECH: the count runs on the model's own query, never on the capped one.
    assert "501" not in q.count_sql


# =============================================================================
# Refused queries: each one an attack or a mistake
# =============================================================================

@pytest.mark.parametrize("sql, reason", [
    ("SELECT 1; DROP TABLE loans", "exactly one statement"),           # stacked statements
    ("DELETE FROM loans", "Only SELECT"),                              # a write
    ("INSERT INTO loans SELECT * FROM loans", "Only SELECT"),
    ("UPDATE loans SET fico = 850", "Only SELECT"),
    ("CREATE TABLE x AS SELECT 1", "Only SELECT"),
    ("COPY loans TO 'out.csv'", "Only SELECT"),                        # file write
    ("ATTACH 'other.db'", "Only SELECT"),
    ("PRAGMA database_list", "Only SELECT"),
    ("SET enable_external_access = true", "Only SELECT"),             # switching off safety
    ("WITH t AS (SELECT 1) SELECT * FROM t", "Not allowed"),           # CTE
    ("SELECT fico FROM loans UNION SELECT 1", "Only SELECT"),          # UNION
    ("SELECT * FROM read_csv('C:/Windows/win.ini')", "Not allowed"),   # file read
    ("SELECT * FROM 'x.parquet'", "Unknown table"),                    # file as a table
    ("SELECT * FROM other_table", "Unknown table"),
    ("SELECT * FROM main.loans", "Unknown table"),                     # schema prefix
    ("SELECT getenv('HOME')", "Not allowed"),                          # unknown function
    ("SELECT purpose FROM loans", "Unknown column"),                   # typo'd column
    ("SELECT x.fico FROM loans", "Unknown table or alias"),
    ("SELECT fico FROM loans -- comment", "comments"),
    ("SELECT /* hi */ fico FROM loans", "comments"),
    ("", "empty"),
    ("SELEC fico FROM", "parsed"),
    ("SELECT fico FROM loans LIMIT fico", "whole number"),
    ("SELECT ROW_NUMBER() OVER (ORDER BY fico) FROM loans", "Not allowed"),  # windows not listed
])
def test_unsafe_or_broken_queries_are_refused(sql: str, reason: str) -> None:
    """BUSINESS: anything that is not one plain read of the tape is refused, with a
    reason the model can act on (it goes back to the model as the tool result)."""
    with pytest.raises(GuardrailError, match=reason):
        guard(sql)


def test_overlong_sql_is_refused() -> None:
    """BUSINESS: a runaway model cannot send a megabyte of SQL."""
    with pytest.raises(GuardrailError, match="longer than"):
        check_query("SELECT fico FROM loans WHERE " + " OR ".join(["fico > 1"] * 500),
                    COLUMNS, max_rows=500, max_chars=200)


# =============================================================================
# The read-only connection: the last line of defence
# =============================================================================

@pytest.mark.parametrize("sql", [
    "CREATE TABLE x (a INT)",
    "DELETE FROM loans",
    "SELECT * FROM read_csv('C:/Windows/win.ini')",
    "COPY loans TO 'out.csv'",
    "SET enable_external_access = true",
    "ATTACH 'other.duckdb' AS other",
])
def test_readonly_tape_refuses_writes_and_files_even_without_the_guard(
        ro_tape: ReadOnlyTape, sql: str) -> None:  # noqa: F811
    """BUSINESS: even a query that slipped past the guard cannot change the tape or
    touch the server's files: the database itself says no."""
    with pytest.raises(duckdb.Error):
        ro_tape.con.execute(sql)


def test_guarded_query_runs_on_the_readonly_tape(ro_tape: ReadOnlyTape) -> None:  # noqa: F811
    """BUSINESS: the bound values give the same answer as the literal query would.

    TECH: string, integer and Decimal parameters all bind against VARCHAR, DOUBLE
      and DECIMAL columns; a date string binds against a DATE column.
    """
    q = check_query("SELECT COUNT(*) FROM loans WHERE ltv > 125 AND current_upb > 0.5 "
                    "AND orig_date >= '2015-01-01' AND state <> 'ZZ'",
                    ["ltv", "current_upb", "orig_date", "state"], max_rows=500, max_chars=4000)
    expected = ro_tape.con.execute("SELECT COUNT(*) FROM loans WHERE ltv > 125").fetchone()[0]
    assert ro_tape.con.execute(q.sql, q.params).fetchone()[0] == expected > 0
