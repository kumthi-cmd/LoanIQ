"""Tests for the Loan Tape screen's panels and desk questions.

Covers app/tape_panels.py (program mix, note-rate buckets, MBA delinquency, chip
counts, the tape line), app/desk_questions.py (loading and validating the rules) and
the routes in main.py that serve them: /api/tape, /api/loans/breakdowns,
/api/loans/questions and /api/loans?question=.

BUSINESS: the panels are the desk's first read of a tape's shape. These tests protect:
  every loan lands in exactly one note-rate bucket (no balance lost at an edge), the
  program and status totals add back to the whole tape to the cent, every chip count
  equals the number of loans the grid shows when that chip is clicked, a question
  combines with the grid's filters (New York AND FICO under 700), and a broken or
  unsafe rule in the config stops the API instead of showing a wrong count.
TECH: pytest + FastAPI's TestClient. Expected answers come from pandas or a separate
  DuckDB connection over the same Parquet file, so the API is checked against an
  independent source. Edge cases use a small hand-built DuckDB table.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Iterator

import duckdb
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import loan_tape_gen as gen
from app import main
from app.desk_questions import DeskQuestion, load_desk_questions
from app.spec_stories import UnsafeWhereError
from app.tape_panels import (BucketSpec, bucket_spec, fetch_breakdowns, fetch_question_counts,
                             fetch_tape_info, question_counts_sql)

CONTENT_QUESTIONS = gen.REPO_ROOT / "content" / "desk-questions.json"
BREAKDOWNS = main.API_CONFIG["breakdowns"]


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(scope="module")
def data_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A temp folder; the API generates the default tape into it at start-up."""
    return tmp_path_factory.mktemp("panels_tape")


@pytest.fixture(scope="module")
def client(data_dir: Path) -> Iterator[TestClient]:
    """The API over the default synthetic tape, shared by the module."""
    with TestClient(main.create_app(data_dir)) as c:
        yield c


@pytest.fixture(scope="module")
def tape(client: TestClient, data_dir: Path) -> pd.DataFrame:
    """The same tape read with pandas, as the independent source of expected answers."""
    return pd.read_parquet(data_dir / main.TAPE_FILE)


@pytest.fixture(scope="module")
def duck(client: TestClient, data_dir: Path) -> Iterator[duckdb.DuckDBPyConnection]:
    """A separate DuckDB connection over the same Parquet, for hand-written counts."""
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE loans AS SELECT * FROM read_parquet(?)",
                [str(data_dir / main.TAPE_FILE)])
    yield con
    con.close()


def small_table(rows: list[tuple[float, str, str, str, str]]) -> duckdb.DuckDBPyConnection:
    """A tiny `loans` table: (note_rate %, current_upb $, program, dq_status, seller).

    TECH: current_upb as DECIMAL(14,2), like the real tape, so sums stay exact.
      An empty list gives an empty table (DuckDB's executemany refuses zero rows).
    """
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE loans (note_rate DOUBLE, current_upb DECIMAL(14,2), "
                "program VARCHAR, dq_status VARCHAR, seller VARCHAR)")
    if rows:
        con.executemany("INSERT INTO loans VALUES (?, ?, ?, ?, ?)", rows)
    return con


def write_questions(tmp_path: Path, body: str) -> Path:
    """Write a desk-question config to a temp file and return its path."""
    path = tmp_path / "desk_questions.toml"
    path.write_text(body, encoding="utf-8")
    return path


# =============================================================================
# Desk questions: config loading and validation
# =============================================================================

def test_real_config_loads_and_matches_the_content_labels() -> None:
    """BUSINESS: every chip on screen has a rule, and every rule has a label, in the
      same order (rules in config, words in content/, .claude/rules/showcase.md)."""
    questions = load_desk_questions(gen.COLUMNS)
    labels = json.loads(CONTENT_QUESTIONS.read_text(encoding="utf-8"))["questions"]
    assert list(questions) == [q["id"] for q in labels]
    assert all(q["label"] for q in labels)


@pytest.mark.parametrize("where, message", [
    ("ltv > 125; DROP TABLE loans", "semicolons"),
    ("ltv > 125 -- comment", "comments"),
    ("ltv IN (SELECT ltv FROM loans)", "not allowed"),
    ("lower(state) = 'ny'", "not allowed"),
    ("no_such_column > 1", "unknown column"),
    ("ltv", "true/false test"),
])
def test_unsafe_rule_is_rejected_with_the_question_id(tmp_path: Path, where: str, message: str) -> None:
    """BUSINESS: a rule that is not a plain test on tape fields stops start-up, and the
      error says which question to fix. TECH: the same allowlist as the spec stories."""
    path = write_questions(tmp_path, f'[[question]]\nid = "bad_one"\nwhere = "{where}"\n')
    with pytest.raises(UnsafeWhereError, match=rf"Desk question bad_one: .*{message}"):
        load_desk_questions(gen.COLUMNS, path)


@pytest.mark.parametrize("body, message", [
    ('[[question]]\nid = "a"\nwhere = "ltv > 1"\n[[question]]\nid = "a"\nwhere = "fico > 1"\n', "Duplicate"),
    ('[[question]]\nid = "Has Space"\nwhere = "ltv > 1"\n', "id must be"),
    ('[[question]]\nid = "1st"\nwhere = "ltv > 1"\n', "id must be"),
    ('[[question]]\nid = "a"\n', "missing"),
    ('[[question]]\nid = "a"\nwhere = "ltv > 1"\nlabel = "A"\n', "unknown keys"),
    ('[[question]]\nid = "a"\nwhere = 5\n', "must be text"),
])
def test_malformed_entry_is_rejected(tmp_path: Path, body: str, message: str) -> None:
    """BUSINESS: typos in the config are caught at start-up, not when a chip is clicked."""
    with pytest.raises(ValueError, match=message):
        load_desk_questions(gen.COLUMNS, write_questions(tmp_path, body))


def test_api_does_not_start_with_a_broken_question(tmp_path: Path, data_dir: Path,
                                                   client: TestClient) -> None:
    """BUSINESS: no API at all is better than a chip with a wrong count.
    TECH: the lifespan raises inside `with TestClient(...)`; the tape is reused."""
    broken = write_questions(tmp_path, '[[question]]\nid = "x"\nwhere = "no_such > 1"\n')
    with pytest.raises(UnsafeWhereError):
        with TestClient(main.create_app(data_dir, questions_path=broken)):
            pass


# =============================================================================
# Desk questions: counts and the grid filter
# =============================================================================

# BUSINESS: each rule written out by hand, independently of the config, so a changed
#   rule in desk_questions.toml shows up as a failing test to review.
HAND_WRITTEN = {
    "ltv_over_125": "ltv > 125",
    "new_york": "state = 'NY'",
    "puerto_rico": "state = 'PR'",
    "seriously_delinquent": "dq_status IN ('90', '120+', 'FC', 'REO', 'BK')",
    "modified": "mod_flag",
    "forbearance": "forbearance_flag",
}


def test_chip_counts_match_hand_written_rules(client: TestClient, duck: duckdb.DuckDBPyConnection) -> None:
    """BUSINESS: "LTV over 125: 20" really is every loan above 125 LTV, and so on for
      every chip; UPB is exact to the cent. Each count must be above 0, or the chip
      would prove nothing (the generator forces these loans)."""
    counts = client.get("/api/loans/questions").json()
    assert [c["id"] for c in counts] == list(HAND_WRITTEN)
    for c in counts:
        n, upb = duck.execute(f"SELECT COUNT(*), SUM(current_upb) FROM loans "
                              f"WHERE {HAND_WRITTEN[c['id']]}").fetchone()
        assert c["loans"] == n > 0, c["id"]
        assert Decimal(str(c["current_upb"])) == upb, c["id"]


def test_each_chip_count_equals_the_grid_total(client: TestClient) -> None:
    """BUSINESS: clicking a chip shows exactly the number of loans the chip promised."""
    for c in client.get("/api/loans/questions").json():
        page = client.get("/api/loans", params={"question": c["id"], "limit": 500}).json()
        assert page["total"] == c["loans"], c["id"]


def test_question_rows_all_answer_the_question(client: TestClient) -> None:
    """BUSINESS: every loan shown under "New York" is in New York."""
    rows = client.get("/api/loans", params={"question": "new_york", "limit": 500}).json()["rows"]
    assert rows and all(r["state"] == "NY" for r in rows)


def test_question_and_grid_filter_both_hold(client: TestClient, duck: duckdb.DuckDBPyConnection) -> None:
    """BUSINESS: "New York" plus "FICO under 700" typed in the grid is both at once.
    TECH: the filter's OR stays inside its brackets and cannot widen the question."""
    model = {"fico": {"filterType": "number", "operator": "OR", "conditions": [
        {"filterType": "number", "type": "lessThan", "filter": 700},
        {"filterType": "number", "type": "greaterThan", "filter": 800}]}}
    resp = client.get("/api/loans", params={"question": "new_york", "filter": json.dumps(model)})
    expected = duck.execute("SELECT COUNT(*) FROM loans WHERE state = 'NY' "
                            "AND (fico < 700 OR fico > 800)").fetchone()[0]
    assert resp.json()["total"] == expected


@pytest.mark.parametrize("question", ["no_such_question", "ltv > 0", "new_york' OR 1=1 --"])
def test_unknown_question_is_400(client: TestClient, question: str) -> None:
    """BUSINESS: a stale or typed-in question is an error, never the whole tape.
    TECH: the id is a dictionary key; SQL sent as a question id is just an unknown id."""
    resp = client.get("/api/loans", params={"question": question})
    assert resp.status_code == 400
    assert "Unknown desk question" in resp.json()["detail"]


def test_blank_question_means_no_question(client: TestClient) -> None:
    """TECH: ?question= with no value is the whole tape, like an empty filter."""
    total = client.get("/api/loans", params={"question": ""}).json()["total"]
    assert total == client.get("/api/health").json()["loans"]


def test_no_questions_gives_no_chips() -> None:
    """TECH: an empty config is allowed: no chips, and no query is run."""
    con = small_table([])
    assert fetch_question_counts(con, []) == []
    assert question_counts_sql([]) == "SELECT 1 FROM loans"
    con.close()


def test_counts_of_an_empty_tape_are_zero() -> None:
    """TECH: zero loans gives 0 and $0 per question, not null."""
    con = small_table([])
    counts = fetch_question_counts(con, [DeskQuestion("low_rate", "note_rate < 3")])
    con.close()
    assert [(c.loans, c.current_upb) for c in counts] == [(0, 0.0)]


# =============================================================================
# Breakdowns: program mix, note-rate buckets, MBA delinquency
# =============================================================================

def test_program_mix_matches_pandas_to_the_cent(client: TestClient, tape: pd.DataFrame) -> None:
    """BUSINESS: the Program mix bars add back to the whole tape, largest first."""
    body = client.get("/api/loans/breakdowns").json()["programs"]
    expected = tape.groupby("program")["current_upb"].agg(["count", "sum"])
    assert {p["program"] for p in body} == set(expected.index)
    for p in body:
        assert p["loans"] == expected.at[p["program"], "count"]
        assert Decimal(str(p["current_upb"])) == expected.at[p["program"], "sum"]
    upbs = [p["current_upb"] for p in body]
    assert upbs == sorted(upbs, reverse=True)


def test_note_rate_buckets_match_pandas(client: TestClient, tape: pd.DataFrame) -> None:
    """BUSINESS: each half-point bar holds exactly the loans in its rate range, and the
      bars add back to every loan and every dollar of the tape."""
    buckets = client.get("/api/loans/breakdowns").json()["note_rates"]
    spec = main.RATE_BUCKETS
    assert len(buckets) == spec.count
    for b in buckets:
        in_bucket = pd.Series(True, index=tape.index)
        if b["low"] is not None:
            in_bucket &= tape["note_rate"] >= b["low"]
        if b["high"] is not None:
            in_bucket &= tape["note_rate"] < b["high"]
        assert b["loans"] == int(in_bucket.sum()), b
    assert sum(b["loans"] for b in buckets) == len(tape)
    total = sum(Decimal(str(b["current_upb"])) for b in buckets)
    assert total == sum(tape["current_upb"])


def test_bucket_edges_and_open_ends() -> None:
    """BUSINESS: a rate exactly on an edge (6.000) goes in the bucket it starts
      (6.0-6.5), a rate below the first edge goes in the first bucket and one above
      the last edge in the last, so no loan is dropped from the chart.
    TECH: 2.0-9.0+ in 0.5 steps gives 15 buckets."""
    rows = [(r, "100.00", "FHA", "Current", "S") for r in
            (1.25, 2.0, 2.499, 2.5, 6.0, 6.125, 8.999, 9.0, 12.5)]
    con = small_table(rows)
    out = fetch_breakdowns(con, BucketSpec(0.5, 2.0, 9.0), ["Current"]).note_rates
    con.close()
    loans = {(b.low, b.high): b.loans for b in out}
    assert len(out) == 15
    assert (out[0].low, out[0].high) == (None, 2.5)
    assert (out[-1].low, out[-1].high) == (9.0, None)
    assert loans[(None, 2.5)] == 3      # 1.25, 2.0, 2.499
    assert loans[(2.5, 3.0)] == 1       # 2.5 on its lower edge
    assert loans[(6.0, 6.5)] == 2       # 6.0 on its lower edge, 6.125
    assert loans[(8.5, 9.0)] == 1       # 8.999
    assert loans[(9.0, None)] == 2      # 9.0 and 12.5
    assert sum(loans.values()) == len(rows)


def test_dq_status_follows_config_order_and_matches_pandas(client: TestClient, tape: pd.DataFrame) -> None:
    """BUSINESS: the delinquency panel reads Current, 30, 60 ... in the MBA order the
      desk uses, and its counts add back to every loan."""
    body = client.get("/api/loans/breakdowns").json()["dq_status"]
    assert [s["status"] for s in body][:len(BREAKDOWNS["dq_status_order"])] == BREAKDOWNS["dq_status_order"]
    counts = tape["dq_status"].value_counts()
    for s in body:
        assert s["loans"] == int(counts.get(s["status"], 0)), s["status"]
    assert sum(s["loans"] for s in body) == len(tape)


def test_status_missing_from_config_still_shows_and_empty_status_shows_zero() -> None:
    """BUSINESS: a status the config forgot is still counted (never hidden), and a
      tracked status with no loans shows 0 instead of disappearing."""
    con = small_table([(5.0, "100.00", "VA", "Current", "S"), (5.0, "50.00", "VA", "XYZ", "S")])
    out = fetch_breakdowns(con, BucketSpec(0.5, 2.0, 9.0), ["Current", "30"]).dq_status
    con.close()
    assert [(s.status, s.loans, s.current_upb) for s in out] == [
        ("Current", 1, 100.0), ("30", 0, 0.0), ("XYZ", 1, 50.0)]


def test_breakdowns_of_an_empty_tape() -> None:
    """TECH: no loans gives no program bars, and zero in every bucket and status."""
    con = small_table([])
    out = fetch_breakdowns(con, BucketSpec(0.5, 2.0, 9.0), ["Current", "30"])
    con.close()
    assert out.programs == []
    assert len(out.note_rates) == 15 and all(b.loans == 0 for b in out.note_rates)
    assert [(s.status, s.loans) for s in out.dq_status] == [("Current", 0), ("30", 0)]


@pytest.mark.parametrize("cfg", [
    {"note_rate_bucket_width": 0, "note_rate_first_bucket_low": 2, "note_rate_last_bucket_low": 9},
    {"note_rate_bucket_width": 0.5, "note_rate_first_bucket_low": 9, "note_rate_last_bucket_low": 2},
    {"note_rate_bucket_width": 0.5, "note_rate_first_bucket_low": 2, "note_rate_last_bucket_low": 2},
    {"note_rate_bucket_width": 0.4, "note_rate_first_bucket_low": 2, "note_rate_last_bucket_low": 9},
])
def test_bad_bucket_settings_are_rejected(cfg: dict[str, float]) -> None:
    """BUSINESS: a bucket typo in api.toml stops start-up rather than draw a
      misleading chart (zero width, edges reversed, or edges not a whole number of steps)."""
    with pytest.raises(ValueError, match="note-rate buckets"):
        bucket_spec(cfg)


def test_real_bucket_settings() -> None:
    """TECH: api.toml gives 2.0% to 9.0%+ in half points: 15 buckets."""
    assert main.RATE_BUCKETS == BucketSpec(0.5, 2.0, 9.0) and main.RATE_BUCKETS.count == 15


# =============================================================================
# The tape line
# =============================================================================

def test_tape_info_counts_fields_and_sellers(client: TestClient, tape: pd.DataFrame) -> None:
    """BUSINESS: "41 fields · 6 fictional sellers" comes from the real tape."""
    assert client.get("/api/tape").json() == {
        "loans": len(tape), "fields": len(gen.COLUMNS), "sellers": tape["seller"].nunique()}


def test_tape_info_of_an_empty_tape() -> None:
    """TECH: no loans means no sellers (0), not an error."""
    con = small_table([])
    info = fetch_tape_info(con, field_count=5)
    con.close()
    assert (info.loans, info.fields, info.sellers) == (0, 5, 0)
