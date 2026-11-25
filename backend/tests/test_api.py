"""Tests for the loan API (backend/app/main.py) and its SQL builder (app/loan_query.py).

BUSINESS: the grid is the desk's first view of a tape. These tests protect what a
  trader relies on: a page shows exactly the loans it claims, sorting and filtering
  match the data (LTV > 125 means LTV > 125), nothing a user types can change the
  SQL, balances arrive as numbers to the cent, the headline WAC / WA FICO / WA LTV
  are UPB-weighted correctly, and a page comes back fast on a 50,000-loan tape.
TECH: pytest + FastAPI's TestClient, which calls the app in-process (no server).
  `with TestClient(app)` runs the app's lifespan, so start-up loading is tested too.
  Each fixture works in its own temp folder; the real data/ folder is never touched.
  Expected answers come from a separate DuckDB connection or pandas reading the same
  Parquet file, so the API is checked against an independent source.
"""

from __future__ import annotations

import json
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator

import duckdb
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import loan_tape_gen as gen
from app import main
from app.loan_query import QueryError, column_kind, parse_filter, parse_sort
from app.slotting import SLOT_COLUMNS

GEN_CFG = gen.load_config()
PERF = main.API_CONFIG["performance"]


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(scope="module")
def data_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """An empty temp folder. TECH: the API generates the default tape into it at start-up."""
    return tmp_path_factory.mktemp("tape")


@pytest.fixture(scope="module")
def client(data_dir: Path) -> Iterator[TestClient]:
    """The API over a tape it generated itself (generator defaults), shared by the module.

    TECH: starting from an empty folder exercises the "file missing -> generate" path.
    """
    with TestClient(main.create_app(data_dir)) as c:
        yield c


@pytest.fixture(scope="module")
def duck(client: TestClient, data_dir: Path) -> Iterator[duckdb.DuckDBPyConnection]:
    """An independent DuckDB connection over the same Parquet, for expected answers."""
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE loans AS SELECT * FROM read_parquet(?)",
                [str(data_dir / main.TAPE_FILE)])
    yield con
    con.close()


def get_loans(client: TestClient, **params: Any) -> Any:
    """GET /api/loans with filter dicts encoded as JSON; returns the response."""
    if isinstance(params.get("filter"), dict):
        params["filter"] = json.dumps(params["filter"])
    return client.get("/api/loans", params=params)


def ids(response: Any) -> list[str]:
    """Loan IDs of a 200 response, in order."""
    assert response.status_code == 200, response.text
    return [r["loan_id"] for r in response.json()["rows"]]


def count(duck: duckdb.DuckDBPyConnection, where: str, params: list[Any] | None = None) -> int:
    """Direct DuckDB count for a hand-written WHERE (test-only; constants, no user input)."""
    return duck.execute(f"SELECT COUNT(*) FROM loans WHERE {where}", params or []).fetchone()[0]


# =============================================================================
# Test tooling
# =============================================================================

def test_testclient_runs_on_httpx2() -> None:
    """TECH: Starlette 1.10 deprecates the old httpx package behind TestClient. This
      fails if requirements.txt's httpx2 is not installed and the old one is used."""
    import starlette.testclient as starlette_testclient
    assert starlette_testclient.httpx.__name__ == "httpx2"


# =============================================================================
# Start-up, health and columns
# =============================================================================

def test_missing_tape_is_generated_with_defaults(client: TestClient, data_dir: Path) -> None:
    """BUSINESS: a fresh checkout still opens on the standard demo tape (default size)."""
    assert (data_dir / main.TAPE_FILE).exists()
    assert client.get("/api/health").json() == {"status": "ok",
                                                "loans": GEN_CFG["run"]["n_default"]}


def test_columns_list_every_tape_column_with_type_and_label(client: TestClient) -> None:
    """BUSINESS: the grid shows every published tape field with a readable header,
    then the columns product slotting adds (Step 5a), never shown by default."""
    cols = client.get("/api/loans/columns").json()
    assert [c["name"] for c in cols] == gen.COLUMNS + SLOT_COLUMNS
    assert all(not c["default_visible"] and c["label"] != c["name"]
               for c in cols if c["name"] in SLOT_COLUMNS)
    by_name = {c["name"]: c for c in cols}
    assert by_name["current_upb"] == {"name": "current_upb", "type": "DECIMAL(14,2)",
                                      "kind": "number", "label": "Current UPB ($)",
                                      "default_visible": True}
    assert by_name["state"]["kind"] == "text"
    assert by_name["orig_date"]["kind"] == "date"
    assert by_name["mod_flag"]["kind"] == "boolean"


def test_columns_mark_the_configured_defaults(client: TestClient) -> None:
    """BUSINESS: the Loan Tape opens on the fields a trader reads first, and the list
    comes from ONE place (api.toml [columns]) that Ask the Tape uses too (Step 4c).

    TECH: exactly the configured names are default_visible, all of them real tape
      columns, in tape order with loan_id first.
    """
    cols = client.get("/api/loans/columns").json()
    shown = [c["name"] for c in cols if c["default_visible"]]
    assert set(shown) == set(main.DEFAULT_VISIBLE_COLUMNS) and len(shown) == 12
    assert shown == [n for n in gen.COLUMNS if n in shown] and shown[0] == "loan_id"


def test_default_columns_drop_unknown_and_repeated_names() -> None:
    """BUSINESS: a typo in the display config hides a column; it never breaks the tape.

    TECH: default_columns follows tape order and drops names the tape lacks and repeats.
    """
    tape = {"loan_id": "VARCHAR", "fico": "INTEGER", "ltv": "DOUBLE"}
    assert main.default_columns(tape, ["loan_id", "nope", "ltv", "fico", "ltv"]) == ["loan_id", "fico", "ltv"]


def test_labels_file_covers_exactly_the_tape_columns() -> None:
    """BUSINESS: no grid header falls back to a raw field name, and no stale labels linger."""
    assert set(main.load_labels()) == set(gen.COLUMNS)


# =============================================================================
# Paging and sorting
# =============================================================================

def test_paging_returns_the_right_slice(client: TestClient, duck: duckdb.DuckDBPyConnection) -> None:
    """BUSINESS: page 3 of "largest balance first" is exactly loans 101-150 in that order."""
    expected = [r[0] for r in duck.execute(
        "SELECT loan_id FROM loans ORDER BY current_upb DESC, loan_id LIMIT 50 OFFSET 100"
    ).fetchall()]
    resp = get_loans(client, offset=100, limit=50, sort="current_upb:desc")
    assert ids(resp) == expected
    assert resp.json()["total"] == GEN_CFG["run"]["n_default"]


def test_pages_neither_overlap_nor_skip(client: TestClient) -> None:
    """BUSINESS: scrolling page to page shows every loan once. Many loans share a
      FICO, so this relies on the loan_id tie-break."""
    page1 = ids(get_loans(client, offset=0, limit=100, sort="fico:asc"))
    page2 = ids(get_loans(client, offset=100, limit=100, sort="fico:asc"))
    both = ids(get_loans(client, offset=0, limit=200, sort="fico:asc"))
    assert page1 + page2 == both
    assert len(set(both)) == 200


def test_default_page_size_comes_from_config(client: TestClient) -> None:
    """TECH: no ?limit= returns default_limit rows (api.toml)."""
    assert len(ids(get_loans(client))) == main.API_CONFIG["paging"]["default_limit"]


@pytest.mark.parametrize("column", ["current_upb", "note_rate", "fico", "seller"])
@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_sort_orders_rows(client: TestClient, column: str, direction: str) -> None:
    """BUSINESS: sorting by balance, rate, FICO or seller really orders the tape."""
    rows = get_loans(client, limit=500, sort=f"{column}:{direction}").json()["rows"]
    values = [r[column] for r in rows]
    assert values == sorted(values, reverse=(direction == "desc"))


def test_multi_column_sort(client: TestClient, duck: duckdb.DuckDBPyConnection) -> None:
    """BUSINESS: "by program, then largest balance" groups the tape the way a desk reads it."""
    expected = [r[0] for r in duck.execute(
        "SELECT loan_id FROM loans ORDER BY program, current_upb DESC, loan_id LIMIT 200"
    ).fetchall()]
    assert ids(get_loans(client, limit=200, sort="program:asc,current_upb:desc")) == expected


def test_nulls_sort_last_both_ways(client: TestClient) -> None:
    """BUSINESS: sorting by ARM margin shows ARMs first; fixed-rate loans (no margin) last."""
    for direction in ("asc", "desc"):
        rows = get_loans(client, limit=500, sort=f"margin:{direction}").json()["rows"]
        assert rows[0]["margin"] is not None


def test_limit_is_capped(client: TestClient) -> None:
    """TECH: one request can never return more than max_limit rows (api.toml)."""
    assert len(ids(get_loans(client, limit=100_000))) == main.MAX_LIMIT


@pytest.mark.parametrize("params", [{"limit": 0}, {"offset": -1}, {"limit": "ten"}])
def test_bad_paging_values_are_rejected(client: TestClient, params: dict[str, Any]) -> None:
    """TECH: Pydantic validation answers 422 for a zero limit, negative offset or non-number."""
    assert get_loans(client, **params).status_code == 422


# =============================================================================
# Filtering
# =============================================================================

def test_ltv_over_125_matches_direct_count(client: TestClient, duck: duckdb.DuckDBPyConnection) -> None:
    """BUSINESS: the high-LTV screen (FHFA high-LTV refis above 125) finds every such
      loan and only those."""
    resp = get_loans(client, filter={"ltv": {"filterType": "number", "type": "greaterThan",
                                             "filter": 125}}, limit=500)
    expected = count(duck, "ltv > 125")
    assert expected > 0  # the generator forces some; otherwise the test proves nothing
    assert resp.json()["total"] == expected
    assert all(r["ltv"] > 125 for r in resp.json()["rows"])


def test_less_than_and_equals(client: TestClient, duck: duckdb.DuckDBPyConnection) -> None:
    """BUSINESS: "FICO under 680" and "exactly 360-month term" match the data."""
    lt = get_loans(client, filter={"fico": {"filterType": "number", "type": "lessThan",
                                            "filter": 680}})
    eq = get_loans(client, filter={"orig_term": {"filterType": "number", "type": "equals",
                                                 "filter": 360}})
    assert lt.json()["total"] == count(duck, "fico < 680")
    assert eq.json()["total"] == count(duck, "orig_term = 360")


@pytest.mark.parametrize(("kind", "value", "sql"), [
    ("greaterThanOrEqual", 700, "fico >= 700"),
    ("lessThanOrEqual", 680, "fico <= 680"),
    ("notEqual", 740, "fico <> 740"),
])
def test_or_equal_and_not_equal(client: TestClient, duck: duckdb.DuckDBPyConnection,
                                kind: str, value: int, sql: str) -> None:
    """BUSINESS: "FICO 700 and up" includes the 700s, as an agent's fico >= 700 does
      (Step 4b: Ask the Tape opens its filter in the Loan Tape, so the grid must
      speak the same comparisons). "Not equal" excludes loans with no value, as SQL does.
    """
    resp = get_loans(client, filter={"fico": {"filterType": "number", "type": kind, "filter": value}})
    assert resp.status_code == 200
    assert resp.json()["total"] == count(duck, sql)


def test_in_range_is_inclusive_on_money(client: TestClient, duck: duckdb.DuckDBPyConnection) -> None:
    """BUSINESS: a loan-balance tier like "$100k to $200k" includes both ends."""
    resp = get_loans(client, filter={"current_upb": {"filterType": "number", "type": "inRange",
                                                     "filter": 100000, "filterTo": 200000}})
    assert resp.json()["total"] == count(duck, "current_upb BETWEEN 100000 AND 200000")


def test_text_contains_is_case_insensitive(client: TestClient, duck: duckdb.DuckDBPyConnection) -> None:
    """BUSINESS: typing "fha" or "FHA" finds the same FHA loans, as in the grid."""
    lower = get_loans(client, filter={"program": {"filterType": "text", "type": "contains",
                                                  "filter": "fha"}})
    upper = get_loans(client, filter={"program": {"filterType": "text", "type": "contains",
                                                  "filter": "FHA"}})
    assert lower.json()["total"] == upper.json()["total"] == count(duck, "program = 'FHA'")


def test_text_equals(client: TestClient, duck: duckdb.DuckDBPyConnection) -> None:
    """BUSINESS: "state equals ny" is the New York story."""
    resp = get_loans(client, filter={"state": {"filterType": "text", "type": "equals",
                                               "filter": "ny"}})
    assert resp.json()["total"] == count(duck, "state = 'NY'") > 0


def test_like_wildcards_in_user_text_match_literally(client: TestClient) -> None:
    """TECH: % and _ typed by the user are characters, not wildcards. No state code
      contains them, so the match is empty (unescaped, '%' would match every loan)."""
    for text in ("%", "_"):
        resp = get_loans(client, filter={"state": {"filterType": "text", "type": "contains",
                                                   "filter": text}})
        assert resp.json()["total"] == 0


def test_combined_or_and_across_columns(client: TestClient, duck: duckdb.DuckDBPyConnection) -> None:
    """BUSINESS: "FICO under 640 OR over 800, AND in New York": OR within a column,
      AND between columns, with brackets in the right place."""
    model = {"fico": {"filterType": "number", "operator": "OR", "conditions": [
                 {"filterType": "number", "type": "lessThan", "filter": 640},
                 {"filterType": "number", "type": "greaterThan", "filter": 800}]},
             "state": {"filterType": "text", "type": "equals", "filter": "NY"}}
    resp = get_loans(client, filter=model)
    assert resp.json()["total"] == count(duck, "(fico < 640 OR fico > 800) AND state = 'NY'")


def test_injection_attempt_is_just_text(client: TestClient) -> None:
    """TECH: values are parameters, so SQL typed into a filter matches nothing and
      changes nothing; the table is still there afterwards."""
    attack = "x'; DROP TABLE loans; --"
    resp = get_loans(client, filter={"seller": {"filterType": "text", "type": "contains",
                                                "filter": attack}})
    assert resp.status_code == 200 and resp.json()["total"] == 0
    assert client.get("/api/health").json()["loans"] == GEN_CFG["run"]["n_default"]


@pytest.mark.parametrize("params", [
    {"filter": {"no_such_col": {"filterType": "number", "type": "equals", "filter": 1}}},
    {"filter": {'ltv" OR 1=1 --': {"filterType": "number", "type": "equals", "filter": 1}}},
    {"sort": "no_such_col:asc"},
    {"sort": "loan_id; DROP TABLE loans"},
])
def test_unknown_column_is_400(client: TestClient, params: dict[str, Any]) -> None:
    """BUSINESS: a typo in a column name is an error, never a silently unfiltered tape.
    TECH: names are checked against the real column list, which also blocks SQL in names."""
    resp = get_loans(client, **params)
    assert resp.status_code == 400
    assert "Unknown column" in resp.json()["detail"]


@pytest.mark.parametrize("params", [
    {"sort": "fico:sideways"},
    {"filter": "{not json"},
    {"filter": "[1, 2]"},
    {"filter": {"ltv": "high"}},
    {"filter": {"ltv": {"filterType": "text", "type": "contains", "filter": "1"}}},
    {"filter": {"state": {"filterType": "number", "type": "equals", "filter": 1}}},
    {"filter": {"orig_date": {"filterType": "date", "type": "equals", "dateFrom": "2024-01-01"}}},
    {"filter": {"ltv": {"filterType": "number", "type": "notBlank", "filter": 80}}},
    {"filter": {"state": {"filterType": "text", "type": "startsWith", "filter": "N"}}},
    {"filter": {"ltv": {"filterType": "number", "type": "equals", "filter": "80"}}},
    {"filter": {"ltv": {"filterType": "number", "type": "equals", "filter": True}}},
    {"filter": {"ltv": {"filterType": "number", "type": "inRange", "filter": 80}}},
    {"filter": {"state": {"filterType": "text", "type": "equals", "filter": 5}}},
    {"filter": {"ltv": {"filterType": "number", "operator": "XOR", "conditions": [
        {"type": "equals", "filter": 80}]}}},
    {"filter": {"ltv": {"filterType": "number", "operator": "AND", "conditions": []}}},
    {"filter": {"ltv": {"filterType": "number", "operator": "AND", "conditions": [80]}}},
])
def test_unsupported_sort_or_filter_is_400(client: TestClient, params: dict[str, Any]) -> None:
    """BUSINESS: a filter the API does not understand is refused, not guessed at."""
    assert get_loans(client, **params).status_code == 400


def test_empty_filter_returns_everything(client: TestClient) -> None:
    """TECH: "{}" or a blank filter means no filter (the grid sends {} when cleared)."""
    total = GEN_CFG["run"]["n_default"]
    assert get_loans(client, filter="{}").json()["total"] == total
    assert get_loans(client, filter="  ").json()["total"] == total


# =============================================================================
# Response format
# =============================================================================

def test_money_is_a_json_number_to_the_cent(client: TestClient, data_dir: Path) -> None:
    """BUSINESS: balances arrive as numbers the grid can sort and total, and equal the
      stored Decimal dollars and cents exactly."""
    resp = get_loans(client, limit=500, sort="loan_id:asc")
    raw = json.loads(resp.text)["rows"]
    tape = pd.read_parquet(data_dir / main.TAPE_FILE).set_index("loan_id")
    for row in raw:
        for col in ("orig_upb", "current_upb", "pi_payment", "appraised_value", "current_value"):
            assert isinstance(row[col], float)
            assert Decimal(str(row[col])).quantize(Decimal("0.01")) == tape.at[row["loan_id"], col]


def test_dates_are_iso_strings(client: TestClient) -> None:
    """TECH: dates serialize as YYYY-MM-DD, the format the schema doc publishes."""
    row = get_loans(client, limit=1).json()["rows"][0]
    assert pd.Timestamp(row["orig_date"]).strftime("%Y-%m-%d") == row["orig_date"]


# =============================================================================
# Summary
# =============================================================================

def test_summary_matches_hand_computed_upb_weighted_averages(client: TestClient, data_dir: Path) -> None:
    """BUSINESS: WAC, WA FICO and WA LTV are weighted by current UPB, total UPB is exact
      to the cent, and every non-Current MBA status counts as delinquent."""
    tape = pd.read_parquet(data_dir / main.TAPE_FILE)
    upb = tape["current_upb"].map(float)
    body = client.get("/api/loans/summary").json()
    assert body["loan_count"] == len(tape)
    assert Decimal(str(body["total_current_upb"])) == sum(tape["current_upb"])
    assert body["wac"] == pytest.approx((tape["note_rate"] * upb).sum() / upb.sum(), abs=0.0005)
    assert body["wa_fico"] == pytest.approx((tape["fico"] * upb).sum() / upb.sum(), abs=0.005)
    assert body["wa_ltv"] == pytest.approx((tape["ltv"] * upb).sum() / upb.sum(), abs=0.005)
    assert body["delinquent_loans"] == int((tape["dq_status"] != "Current").sum()) > 0


def test_summary_of_empty_tape_has_no_averages(client: TestClient, data_dir: Path) -> None:
    """TECH: no loans means no weighted average (null), not a divide-by-zero error."""
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE loans AS SELECT * FROM read_parquet(?) LIMIT 0",
                [str(data_dir / main.TAPE_FILE)])
    summary = main.fetch_summary(main.LoanStore(con=con, columns={}))
    con.close()
    assert (summary.loan_count, summary.total_current_upb, summary.delinquent_loans) == (0, 0, 0)
    assert summary.wac is None and summary.wa_fico is None and summary.wa_ltv is None


# =============================================================================
# SQL builder units (app/loan_query.py)
# =============================================================================

COLS = {"loan_id": "VARCHAR", "fico": "INTEGER", "current_upb": "DECIMAL(14,2)",
        "ltv": "DOUBLE", "orig_date": "DATE", "mod_flag": "BOOLEAN", "geo": "STRUCT(x INT)"}


def test_column_kinds() -> None:
    """TECH: money, integers and doubles are numbers; unknown types fall back to text."""
    assert [column_kind(t) for t in COLS.values()] == [
        "text", "number", "number", "number", "date", "boolean", "text"]


def test_sort_always_ends_with_loan_id_once() -> None:
    """BUSINESS: stable pages: loan_id breaks ties, but is never added twice."""
    assert parse_sort(None, COLS) == '"loan_id" ASC'
    assert parse_sort("fico", COLS) == '"fico" ASC NULLS LAST, "loan_id" ASC'
    assert parse_sort("loan_id:desc", COLS) == '"loan_id" DESC NULLS LAST'


def test_filter_values_never_enter_the_sql_text() -> None:
    """TECH: the SQL holds only ? placeholders; the values travel as parameters."""
    sql, params = parse_filter(json.dumps({"ltv": {"filterType": "number", "type": "inRange",
                                                   "filter": 80, "filterTo": 95}}), COLS)
    assert sql == '"ltv" BETWEEN ? AND ?' and params == [80, 95]
    with pytest.raises(QueryError):
        parse_filter(json.dumps({"geo": {"filterType": "number", "type": "equals",
                                         "filter": 1}}), COLS)


# =============================================================================
# Timing
# =============================================================================

@pytest.fixture(scope="module")
def big_client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    """The API over a 50,000-loan tape (size from api.toml), written to a temp folder.

    TECH: fixed seed so the timing runs on the same tape every time. Building it
      takes a few seconds, once per module.
    """
    folder = tmp_path_factory.mktemp("big_tape")
    gen.write_tape(gen.generate_tape(n=PERF["timing_tape_loans"], seed=7), folder)
    with TestClient(main.create_app(folder)) as c:
        yield c


@pytest.mark.parametrize("params", [
    {},
    {"sort": "current_upb:desc", "offset": 25_000},
    {"sort": "fico:asc", "filter": {"ltv": {"filterType": "number", "type": "greaterThan",
                                            "filter": 80}}},
])
def test_one_page_is_fast_on_50k_loans(big_client: TestClient, params: dict[str, Any]) -> None:
    """BUSINESS: the grid must feel instant on a large seller tape: one page (default
      size), sorted and filtered, under page_budget_ms (api.toml, illustrative).
    TECH: one warm-up call first, so the clock measures the query, not one-time set-up.
      The timed call goes through the full app: validation, SQL, JSON.
    """
    assert get_loans(big_client, **params).status_code == 200  # warm-up
    start = time.perf_counter()
    resp = get_loans(big_client, **params)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert resp.status_code == 200
    assert resp.json()["total"] > 0
    assert elapsed_ms < PERF["page_budget_ms"], f"page took {elapsed_ms:.0f} ms"


@pytest.mark.parametrize("url", ["/api/loans/breakdowns", "/api/loans/questions", "/api/tape",
                                 "/api/loans/slotting"])
def test_panels_are_fast_on_50k_loans(big_client: TestClient, url: str) -> None:
    """BUSINESS: the Loan Tape screen's three panels, chip counts, title line and
      slotting summary (Step 5a) must appear with the grid, not after it: each under
      panels_budget_ms (api.toml, illustrative) on a 50,000-loan tape.
    TECH: same warm-up-then-time pattern as the page test above.
    """
    assert big_client.get(url).status_code == 200  # warm-up
    start = time.perf_counter()
    resp = big_client.get(url)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert resp.status_code == 200
    assert elapsed_ms < PERF["panels_budget_ms"], f"{url} took {elapsed_ms:.0f} ms"
