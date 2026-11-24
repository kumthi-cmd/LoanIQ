"""Tests for loan_tape_link.py: an Ask the Tape answer's SQL -> the Loan Tape's filter.

BUSINESS: "Open in Loan Tape" must show exactly the loans the answer was about,
  written as column filters the trader can read and change. If the filter cannot
  be written that way, the button must say so rather than open the wrong loans.
TECH: unit tests on the translation (each operator and each refusal), then the
  check that matters most: for every translatable query, the grid's own API
  (/api/loans with the produced filter) counts the same loans as DuckDB running
  the agent's WHERE directly.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import main
from app.agent.loan_tape_link import loan_tape_link
from app.loan_query import ColumnTypes
from tests.agent_fixtures import loan_store, tape_dir  # noqa: F401


@pytest.fixture(scope="module")
def columns(loan_store: main.LoanStore) -> ColumnTypes:  # noqa: F811
    """The tape's real columns and DuckDB types."""
    return loan_store.columns


def link(sql: str, columns: ColumnTypes) -> dict[str, Any]:
    """The link as plain data, for short asserts."""
    return loan_tape_link(sql, columns).model_dump()


# =============================================================================
# What translates
# =============================================================================

@pytest.mark.parametrize("where, kind", [
    ("ltv > 125", "greaterThan"), ("ltv >= 125", "greaterThanOrEqual"),
    ("ltv < 80", "lessThan"), ("ltv <= 80", "lessThanOrEqual"),
    ("ltv = 80", "equals"), ("ltv <> 80", "notEqual"),
])
def test_number_comparisons(columns: ColumnTypes, where: str, kind: str) -> None:
    """BUSINESS: "LTV over 125" from the agent becomes the grid's "greater than 125"."""
    out = link(f"SELECT loan_id FROM loans WHERE {where}", columns)
    assert out["filter"] == {"ltv": {"filterType": "number", "type": kind,
                                     "filter": int(where.split()[-1])}}
    assert out["reason"] is None


def test_value_first_comparison_is_flipped(columns: ColumnTypes) -> None:
    """TECH: "125 < ltv" means ltv > 125."""
    assert link("SELECT * FROM loans WHERE 125 < ltv", columns)["filter"]["ltv"]["type"] == "greaterThan"


def test_text_equals_between_in_and_like(columns: ColumnTypes) -> None:
    """BUSINESS: the NY / 30-year / under $150K story from the design board, as column filters."""
    out = link("SELECT loan_id FROM loans WHERE state = 'NY' AND orig_upb BETWEEN 0 AND 150000.5 "
               "AND program IN ('FHA', 'VA') AND seller LIKE '%Finch%'", columns)
    assert out["filter"] == {
        "state": {"filterType": "text", "type": "equals", "filter": "NY"},
        "orig_upb": {"filterType": "number", "type": "inRange", "filter": 0, "filterTo": 150000.5},
        "program": {"filterType": "text", "operator": "OR", "conditions": [
            {"filterType": "text", "type": "equals", "filter": "FHA"},
            {"filterType": "text", "type": "equals", "filter": "VA"}]},
        "seller": {"filterType": "text", "type": "contains", "filter": "Finch"},
    }


def test_two_conditions_on_one_column_are_anded(columns: ColumnTypes) -> None:
    """BUSINESS: "FICO from 620 to under 700" is one column with two conditions."""
    out = link("SELECT * FROM loans WHERE (fico >= 620) AND fico < 700", columns)
    assert out["filter"]["fico"] == {"filterType": "number", "operator": "AND", "conditions": [
        {"filterType": "number", "type": "greaterThanOrEqual", "filter": 620},
        {"filterType": "number", "type": "lessThan", "filter": 700}]}


def test_no_where_opens_the_whole_tape_and_order_by_becomes_sort(columns: ColumnTypes) -> None:
    """BUSINESS: "10 largest balances" opens the whole tape, largest first.
    TECH: LIMIT is ignored; an ORDER BY on an alias stops the sort list."""
    out = link("SELECT loan_id, ltv AS x FROM loans ORDER BY current_upb DESC, fico, x LIMIT 10", columns)
    assert out == {"filter": {}, "sort": "current_upb:desc,fico:asc", "reason": None}
    grouped = link("SELECT seller, COUNT(*) AS n FROM loans WHERE ltv > 1 GROUP BY seller ORDER BY n DESC",
                   columns)
    assert grouped["sort"] is None and grouped["filter"] == {
        "ltv": {"filterType": "number", "type": "greaterThan", "filter": 1}}


def test_negative_number(columns: ColumnTypes) -> None:
    """TECH: -5 parses as a minus sign around 5."""
    assert link("SELECT * FROM loans WHERE fico > -5", columns)["filter"]["fico"]["filter"] == -5


# =============================================================================
# What is refused, with a reason
# =============================================================================

@pytest.mark.parametrize("where, words", [
    ("ltv > 125 OR fico < 600", "OR across conditions"),
    ("dq_status IN ('90', '120+', 'FC')", "3 values"),
    ("fico > 600 AND fico < 700 AND fico <> 650", "more than 2 conditions"),
    ("state IN ('NY', 'PR') AND state = 'NY'", "mixes a list"),
    ("NOT ltv > 125", "has no grid filter"),
    ("ltv IS NULL", "has no grid filter"),
    ("ROUND(ltv) > 125", "not a plain column"),
    ("ltv > fico", "not a plain value"),
    ("state > 'M'", "equal or contains"),
    ("state = 5", "is text but"),
    ("ltv = 'high'", "needs a number"),
    ("seller LIKE 'Alder%'", "only LIKE"),
    ("seller LIKE '%a_b%'", "only LIKE"),
    ("ltv LIKE '%1%'", "only LIKE"),
    ("orig_date > '2024-01-01'", "date column"),
])
def test_untranslatable_filters_give_a_reason(columns: ColumnTypes, where: str, words: str) -> None:
    """BUSINESS: never open the grid on different loans than the answer; say why instead."""
    out = link(f"SELECT loan_id FROM loans WHERE {where}", columns)
    assert out["filter"] is None and words in out["reason"]


@pytest.mark.parametrize("sql, words", [
    ("SELECT seller FROM loans GROUP BY seller HAVING COUNT(*) > 5", "HAVING"),
    ("SELECT * FROM (SELECT * FROM loans WHERE ltv > 1) AS t", "subquery"),
    ("SELECT ((", "could not be read"),
    ("INSERT INTO loans VALUES (1)", "plain SELECT"),
])
def test_query_shapes_that_cannot_open(columns: ColumnTypes, sql: str, words: str) -> None:
    """TECH: group filters, subqueries and unreadable SQL are refused, not half-translated."""
    assert words in link(sql, columns)["reason"]


# =============================================================================
# The grid shows the same loans as the agent's SQL
# =============================================================================

@pytest.fixture(scope="module")
def client(tape_dir: Path) -> Iterator[TestClient]:  # noqa: F811
    """The whole app over the seeded tape (no model needed)."""
    with TestClient(main.create_app(tape_dir)) as c:
        yield c


@pytest.mark.parametrize("where", [
    "ltv > 125",
    "state = 'NY' AND orig_upb <= 150000",
    "fico >= 700 AND fico < 760 AND program IN ('FHA', 'VA')",
    "current_upb BETWEEN 100000 AND 200000.25",
    "seller LIKE '%Finch%' AND note_rate <> 4.5",
    "state IN ('PR', 'NY')",
])
def test_grid_counts_the_same_loans_as_the_agent(client: TestClient, loan_store: main.LoanStore,  # noqa: F811
                                                 columns: ColumnTypes, where: str) -> None:
    """BUSINESS: "Open in Loan Tape" shows exactly the loans behind the answer.
    TECH: the produced filter goes through /api/loans (loan_query.py); the count
      must equal DuckDB running the agent's own WHERE on the same tape."""
    out = link(f"SELECT loan_id FROM loans WHERE {where}", columns)
    expected = loan_store.con.execute(f"SELECT COUNT(*) FROM loans WHERE {where}").fetchone()[0]
    grid = client.get("/api/loans", params={"filter": json.dumps(out["filter"]), "limit": 1})
    assert expected > 0  # otherwise the test proves nothing
    assert grid.status_code == 200 and grid.json()["total"] == expected
