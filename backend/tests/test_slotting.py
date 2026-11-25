"""Tests for Product Slotting (app/slotting.py, app/slotting_api.py, config/slotting.toml).

BUSINESS: what a desk relies on before it prices a tape: every loan is either
  slotted into one agency pool with a down and an up coupon, or not slotted with the
  first reason it fails (no agency pool, no TBA product, not current); the coupon
  rule holds to the last decimal; LLB shows only the lowest tier a loan fits, and a
  loan can carry several stories; the seeded tape gives exactly the totals on the
  design board; one run at a time; one shared result that a restart clears; and a
  bad rule stops the app instead of mis-slotting loans.
TECH: pytest and FastAPI's TestClient. The run's event stream is read whole and
  split into (event, data) pairs. Worked examples run the real SQL over a small
  hand-made `loans` table. The seeded tape's slots are also checked loan by loan
  against an independent pandas + Decimal reading of slotting.toml. Config errors
  are tested by writing a changed copy of slotting.toml to a temp folder.
"""

from __future__ import annotations

import json
import time
import tomllib
from decimal import ROUND_FLOOR, Decimal
from pathlib import Path
from typing import Any, Iterator

import duckdb
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import loan_tape_gen as gen
from app import main
from app import slotting as sl
from tests.agent_fixtures import tape_dir  # noqa: F401

REPO = Path(__file__).resolve().parents[2]
SOURCES = (REPO / "docs" / "public-sources.md").read_text(encoding="utf-8")
GEN_CFG = gen.load_config()
PROGRAMS, PRODUCTS = list(GEN_CFG["programs"]), list(GEN_CFG["products"])
PERF = main.API_CONFIG["performance"]
WORDS = sl.load_slotting_words()
BOARD_LOAN = "LN78265415"


# =============================================================================
# Helpers and fixtures
# =============================================================================

def sse(text: str) -> list[tuple[str, dict[str, Any]]]:
    """Split a text/event-stream body into (event type, JSON data) pairs.

    TECH: events are blank-line separated blocks of "event: <type>" and
      "data: <json>" lines (the SSE wire format).
    """
    out = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if "event" in fields:
            out.append((fields["event"], json.loads(fields["data"])))
    return out


def run(client: TestClient) -> list[tuple[str, dict[str, Any]]]:
    """POST /api/slotting/run and return its events. TECH: asserts HTTP 200."""
    resp = client.post("/api/slotting/run")
    assert resp.status_code == 200, resp.text
    return sse(resp.text)


@pytest.fixture(scope="module")
def fresh(tape_dir: Path) -> Iterator[TestClient]:  # noqa: F811
    """The app over the seeded tape, never slotted. TECH: used read-only."""
    with TestClient(main.create_app(tape_dir)) as c:
        yield c


@pytest.fixture(scope="module")
def client(tape_dir: Path) -> Iterator[TestClient]:  # noqa: F811
    """The app over the seeded tape, slotted once by the `events` fixture."""
    with TestClient(main.create_app(tape_dir)) as c:
        yield c


@pytest.fixture(scope="module")
def events(client: TestClient) -> list[tuple[str, dict[str, Any]]]:
    """The events of one full run on the seeded tape."""
    return run(client)


@pytest.fixture(scope="module")
def totals(events: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    """The done event's totals."""
    kind, data = events[-1]
    assert kind == "done"
    return data["totals"]


def loan_row(client: TestClient, loan_id: str) -> dict[str, Any]:
    """One loan's grid row from /api/loans, filtered by its id."""
    flt = {"loan_id": {"filterType": "text", "type": "equals", "filter": loan_id}}
    rows = client.get("/api/loans", params={"filter": json.dumps(flt)}).json()["rows"]
    assert len(rows) == 1
    return rows[0]


# =============================================================================
# The seeded tape matches the design board
# =============================================================================

def test_seeded_tape_totals_match_the_board(totals: dict[str, Any]) -> None:
    """BUSINESS: the numbers on the "5 · Product Slotting" board are the real result:
      1,467 slotted (1,012 UMBS, 455 GNMA II); 533 not (312 no agency pool, 85 ARMs,
      136 delinquent); 363 generic TBA, the rest with at least one story."""
    assert totals["loans"] == 2000
    assert totals["slotted"] == 1467 and totals["not_slotted"] == 533
    assert totals["by_agency"] == {"UMBS": 1012, "GNMA II": 455}
    assert totals["by_reason"] == {"no_agency": 312, "product": 85, "status": 136}
    assert totals["generic_tba"] == 363 and totals["with_story"] == 1467 - 363


def test_seeded_tape_story_counts_match_the_board(totals: dict[str, Any]) -> None:
    """BUSINESS: LLB 974 (55 at the $85K tier), NY 72, PR 17, Low FICO 379; 323 loans
      carry more than one story. A loan counts once per family, at its lowest tier."""
    assert totals["stories"] == {"LLB": 974, "NY": 72, "PR": 17, "LOW_FICO": 379}
    assert totals["tiers"]["LLB"]["LLB_85K"] == 55
    assert sum(totals["tiers"]["LLB"].values()) == 974
    assert totals["multi_story"] == 323


def test_board_loan_fits_three_stories_at_umbs_2_5_and_3_0(client: TestClient, events: Any) -> None:
    """BUSINESS: LN78265415 (NY, $268,800 original balance, FICO 674, note 3.125) fits
      LLB 275K (its lowest tier), NY and Low FICO, at UMBS 2.5 down / 3.0 up."""
    card = client.get(f"/api/loans/{BOARD_LOAN}/slots").json()
    assert card["slotted"] is True and card["agency"] == "UMBS" and card["term"] == "30Y"
    assert (card["down_coupon"], card["up_coupon"]) == ("2.5", "3.0")
    assert card["slot"] == "UMBS 30Y 2.5 / 3.0"
    assert [s["name"] for s in card["stories"]] == ["LLB_275K", "NY", "LOW_FICO"]
    assert [s["label"] for s in card["stories"]] == ["LLB 275K", "NY", "Low FICO"]
    assert card["stories"][0]["rule"] == "orig_upb <= 275000"
    assert card["stories"][0]["why"] == "Original balance $268,800 fits the $275K tier, the lowest it fits"
    assert card["stories"][2]["rule"] == "fico < 700" and "674" in card["stories"][2]["why"]
    assert card["generic_tba"] == "Generic TBA · UMBS 30Y 2.5"
    assert card["loan"]["state"] == "NY" and card["loan"]["note_rate"] == 3.125
    assert card["not_slotted"] is None


# =============================================================================
# The event stream
# =============================================================================

def test_run_streams_13_steps_then_done(events: list[tuple[str, dict[str, Any]]]) -> None:
    """BUSINESS: the visitor watches 13 steps in the board's order, each with a
      commentary line, the progress rising to 100%, then the totals.
    TECH: step numbers 1..13, percent strictly rising, ending at 100."""
    steps = [d for k, d in events if k == "step"]
    assert [k for k, _ in events] == ["step"] * 13 + ["done"]
    assert [s["step"] for s in steps] == list(range(1, 14)) and {s["steps"] for s in steps} == {13}
    assert [s["kind"] for s in steps] == ["load_tape", "load_rules", "agency", "product", "status",
                                          "eligible", "coupons", "story", "story", "story", "story",
                                          "overlaps", "write"]
    percents = [s["percent"] for s in steps]
    assert percents == sorted(set(percents)) and percents[-1] == 100
    assert all(s["name"] and s["line"] for s in steps)


def test_commentary_lines_carry_the_real_counts(events: list[tuple[str, dict[str, Any]]]) -> None:
    """BUSINESS: every commentary line is filled from the run, never from the board's
      samples: the counts here are the seeded tape's."""
    lines = [d["line"] for k, d in events if k == "step"]
    assert lines[0] == "Loaded 2,000 loans from the tape"
    assert lines[1].startswith("Loaded 12 rules in 4 spec stories")
    assert lines[2] == "312 Jumbo and Non-QM loans have no agency pool: not slotted"
    assert lines[3] == "85 loans have no fixed-rate TBA coupon (5/6 ARM, 7/6 ARM, 10/6 ARM): not slotted"
    assert lines[4] == "136 delinquent loans: agency pools take current loans only"
    assert lines[5] == "1,467 loans to slot: 1,012 into UMBS, 455 into GNMA II"
    assert lines[6].endswith("down 1.5 to 8.0, up 2.0 to 8.5")
    assert lines[7] == "LLB: 974 loans fit a low-loan-balance tier, 55 of them the $85K tier"
    assert lines[8:11] == ["NY: 72 loans (state = 'NY')", "PR: 17 loans (state = 'PR')",
                           "Low FICO: 379 loans (fico < 700)"]
    assert lines[11] == "323 loans fit more than one story; the hover lists them all"
    assert lines[12] == "Wrote 1,467 slots to the Loan Tape; 363 loans have no story and go generic TBA"


def test_done_event_is_the_status(client: TestClient, events: list[tuple[str, dict[str, Any]]]) -> None:
    """BUSINESS: after the run, every visitor sees the same result: status gives the
      run time and exactly the totals the done event sent."""
    done = events[-1][1]
    status = client.get("/api/slotting/status").json()
    assert status["run"] is True and status["running"] is False
    assert status["run_at"] == done["run_at"] and status["totals"] == done["totals"]


# =============================================================================
# The Loan Tape before and after a run
# =============================================================================

def test_before_a_run_the_tape_is_unslotted(fresh: TestClient) -> None:
    """BUSINESS: until someone runs slotting, the Loan Tape is the seller's tape:
      status says not run, no slot columns, and the hover card is not available."""
    assert fresh.get("/api/slotting/status").json() == {"run": False, "running": False,
                                                        "run_at": None, "totals": None}
    assert [c["name"] for c in fresh.get("/api/loans/columns").json()] == gen.COLUMNS
    assert "slot" not in loan_row(fresh, BOARD_LOAN)
    assert fresh.get(f"/api/loans/{BOARD_LOAN}/slots").status_code == 409


def test_after_a_run_the_grid_gains_slot_and_spec_stories(client: TestClient, events: Any) -> None:
    """BUSINESS: slotting updates the Loan Tape: two new columns, Slot and Spec
      Stories, at the end, not shown by default until Step 5b decides how."""
    cols = client.get("/api/loans/columns").json()
    assert [c["name"] for c in cols] == gen.COLUMNS + ["slot", "spec_stories"]
    new = {c["name"]: c for c in cols[-2:]}
    assert new["slot"]["label"] == "Slot" and new["spec_stories"]["label"] == "Spec Stories"
    assert all(c["kind"] == "text" and not c["default_visible"] for c in new.values())
    row = loan_row(client, BOARD_LOAN)
    assert (row["slot"], row["spec_stories"]) == ("UMBS 30Y 2.5 / 3.0", "LLB 275K, NY, Low FICO")


@pytest.mark.parametrize("column, value, expected", [
    ("spec_stories", "Generic TBA", 363),
    ("slot", "Not slotted", 533),
    ("spec_stories", "No agency pool", 312),
    ("spec_stories", "No TBA product", 85),
    ("spec_stories", "Delinquent", 136),
])
def test_grid_filters_on_the_slot_columns(client: TestClient, events: Any, column: str,
                                          value: str, expected: int) -> None:
    """BUSINESS: a trader filters the tape to "Generic TBA" or "Not slotted" like any
      column, and the counts agree with the run's totals.
    TECH: the same AG Grid filter path as every column, values bound as parameters."""
    flt = {column: {"filterType": "text", "type": "equals", "filter": value}}
    assert client.get("/api/loans", params={"filter": json.dumps(flt)}).json()["total"] == expected


def test_grid_sorts_by_slot_and_still_counts_every_loan(client: TestClient, events: Any) -> None:
    """BUSINESS: sorting by Slot groups loans by pool; no loan is lost by the join."""
    resp = client.get("/api/loans", params={"sort": "slot:asc", "limit": 5})
    assert resp.status_code == 200 and resp.json()["total"] == 2000
    assert resp.json()["rows"][0]["slot"].startswith("GNMA II")


def test_headline_panels_still_count_the_whole_tape(client: TestClient, events: Any) -> None:
    """BUSINESS: slotting adds columns, never loans or fields: "41 fields" stays 41."""
    assert client.get("/api/tape").json()["fields"] == len(gen.COLUMNS)
    assert client.get("/api/loans/summary").json()["loan_count"] == 2000


# =============================================================================
# The hover card
# =============================================================================

@pytest.mark.parametrize("filter_, reason, short", [
    ({"product": {"filterType": "text", "type": "equals", "filter": "7/6 ARM"},
      "program": {"filterType": "text", "type": "equals", "filter": "Conventional"}}, "product", "No TBA product"),
    ({"program": {"filterType": "text", "type": "equals", "filter": "Jumbo"}}, "no_agency", "No agency pool"),
    ({"slot": {"filterType": "text", "type": "equals", "filter": "Not slotted"},
      "spec_stories": {"filterType": "text", "type": "equals", "filter": "Delinquent"}}, "status", "Delinquent"),
])
def test_card_says_why_a_loan_is_not_slotted(client: TestClient, events: Any, filter_: dict[str, Any],
                                             reason: str, short: str) -> None:
    """BUSINESS: hovering a loan that is not slotted explains why, in plain English:
      Jumbo is above the conforming limit; an ARM has no TBA coupon; a delinquent
      loan names its MBA status."""
    loan = client.get("/api/loans", params={"filter": json.dumps(filter_), "limit": 1}).json()["rows"][0]
    card = client.get(f"/api/loans/{loan['loan_id']}/slots").json()
    assert card["slotted"] is False and card["stories"] == [] and card["down_coupon"] is None
    assert card["not_slotted"]["reason"] == reason and card["not_slotted"]["short"] == short
    text = card["not_slotted"]["text"]
    if reason == "no_agency":
        assert text == WORDS["reasons"]["no_agency"]["by_program"]["Jumbo"]
    else:
        assert (loan["product"] if reason == "product" else loan["dq_status"]) in text


def test_card_for_a_generic_tba_loan_has_no_story(client: TestClient, events: Any) -> None:
    """BUSINESS: a slotted loan with no story still has a pool: generic TBA."""
    flt = {"spec_stories": {"filterType": "text", "type": "equals", "filter": "Generic TBA"}}
    loan = client.get("/api/loans", params={"filter": json.dumps(flt), "limit": 1}).json()["rows"][0]
    card = client.get(f"/api/loans/{loan['loan_id']}/slots").json()
    assert card["slotted"] is True and card["stories"] == []
    assert card["generic_tba"].startswith("Generic TBA · ") and card["generic_note"]


@pytest.mark.parametrize("loan_id, status", [("LN123", 400), ("ln78265415", 400),
                                              ("LN00000000", 404)])
def test_card_refuses_bad_and_unknown_ids(client: TestClient, events: Any, loan_id: str,
                                          status: int) -> None:
    """TECH: a malformed id is a 400 (LN + 8 digits); an id not on the tape a 404."""
    assert client.get(f"/api/loans/{loan_id}/slots").status_code == status


# =============================================================================
# One run at a time, one shared result, gone after a restart
# =============================================================================

def test_a_second_run_while_one_is_going_gets_409(client: TestClient, events: Any) -> None:
    """BUSINESS: two visitors can't overlap runs on the shared tape.
    TECH: holding the lock stands in for a run in progress."""
    service = client.app.state.slotting
    with service.lock:
        resp = client.post("/api/slotting/run")
        assert resp.status_code == 409
        assert resp.json()["detail"] == WORDS["errors"]["busy"]
        assert client.get("/api/slotting/status").json()["running"] is True


def test_a_run_that_loses_the_race_gets_an_error_event(client: TestClient, events: Any) -> None:
    """TECH: if the lock is taken between the 409 check and the stream, the stream
      sends one error event and changes nothing."""
    service = client.app.state.slotting
    before = service.run_at
    with service.lock:
        out = list(service.stream())
    assert [(e.event, e.data) for e in out] == [("error", {"message": WORDS["errors"]["busy"]})]
    assert service.run_at == before


def test_a_run_stopped_early_keeps_the_last_result(client: TestClient, events: Any) -> None:
    """BUSINESS: if a visitor closes the dialog mid-run, the Loan Tape keeps the last
      finished result and the next run can start.
    TECH: closing the generator raises GeneratorExit inside it; the finally blocks
      drop the staging table and release the lock."""
    service = client.app.state.slotting
    before = (service.run_at, service.totals)
    stream = service.stream()
    for _ in range(4):  # TECH: past step 3, which writes the staging table
        next(stream)
    stream.close()
    assert not service.lock.locked() and (service.run_at, service.totals) == before
    tables = {r[0] for r in service.con.execute("SELECT table_name FROM duckdb_tables()").fetchall()}
    assert sl.STAGING not in tables and sl.SLOTS in tables


def test_a_run_that_fails_sends_an_error_and_keeps_the_last_result(
        client: TestClient, events: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """BUSINESS: if the engine fails partway, the visitor is told plainly, the Loan
      Tape keeps the last finished run, and the next run can start.
    TECH: monkeypatch makes one step raise a DuckDB error for this test only."""
    service = client.app.state.slotting
    before = (service.run_at, service.totals)

    def broken(self: sl.SlottingRun, cur: Any) -> dict[str, str]:
        raise duckdb.Error("disk on fire")
    monkeypatch.setattr(sl.SlottingRun, "step_coupons", broken)
    out = sse(client.post("/api/slotting/run").text)
    assert [k for k, _ in out] == ["step"] * 6 + ["error"]
    assert out[-1][1] == {"message": WORDS["errors"]["failed"]}
    assert (service.run_at, service.totals) == before and not service.lock.locked()
    assert loan_row(client, BOARD_LOAN)["slot"] == "UMBS 30Y 2.5 / 3.0"


def test_a_second_run_replaces_the_first_with_the_same_result(client: TestClient, events: Any) -> None:
    """BUSINESS: same tape, same rules, same answer; only the run time moves on."""
    again = run(client)
    assert again[-1][1]["totals"] == events[-1][1]["totals"]
    assert again[-1][1]["run_at"] >= events[-1][1]["run_at"]
    assert not client.app.state.slotting.lock.locked()


def test_a_restart_forgets_the_result(tape_dir: Path) -> None:  # noqa: F811
    """BUSINESS: the result lives in memory like the tape: after a restart the status
      says not run and the grid has no slot columns until the next run."""
    with TestClient(main.create_app(tape_dir)) as c:
        run(c)
        assert c.get("/api/slotting/status").json()["run"] is True
    with TestClient(main.create_app(tape_dir)) as c:
        assert c.get("/api/slotting/status").json()["run"] is False
        assert [col["name"] for col in c.get("/api/loans/columns").json()] == gen.COLUMNS


def test_ask_the_tape_copy_has_no_slot_columns(client: TestClient, events: Any) -> None:
    """BUSINESS: Ask the Tape reads the seller's tape only in Step 5a (a follow-up)."""
    con = client.app.state.ask.tape.con
    cols = [r[0] for r in con.execute("DESCRIBE loans").fetchall()]
    assert cols == gen.COLUMNS


# =============================================================================
# Every loan, checked independently against slotting.toml
# =============================================================================

def expected_slot(loan: pd.Series, cfg: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    """(reason, down, up) for one loan, read straight from slotting.toml with Decimal.

    BUSINESS: the same three checks in the same order, and
      down = FLOOR((note - strip) / step) x step, up = down + step, in percent.
    """
    pools = {p for agency, progs in cfg["agencies"].items() if agency != "none" for p in progs}
    if loan.program not in pools:
        return "no_agency", None, None
    if loan["product"] not in cfg["products"]:
        return "product", None, None
    if loan.dq_status != cfg["status"]["eligible"]:
        return "status", None, None
    strip = Decimal(str(cfg["coupons"]["min_strip_pct"]))
    step = Decimal(str(cfg["coupons"]["coupon_step_pct"]))
    down = ((Decimal(str(loan.note_rate)) - strip) / step).to_integral_value(ROUND_FLOOR) * step
    return None, f"{down:.1f}", f"{down + step:.1f}"


def test_every_loan_matches_an_independent_reading(client: TestClient, events: Any, tape_dir: Path) -> None:  # noqa: F811
    """BUSINESS: every one of the 2,000 loans gets the reason and coupons the rules
      say, not just the totals.
    TECH: pandas reads the Parquet tape and Python's Decimal does the arithmetic,
      independent of the DuckDB SQL under test."""
    with sl.SLOTTING_PATH.open("rb") as f:
        cfg = tomllib.load(f)
    tape = pd.read_parquet(tape_dir / main.TAPE_FILE).set_index("loan_id")
    got = client.app.state.store.con.execute(
        "SELECT loan_id, reason, CAST(down_coupon AS VARCHAR), CAST(up_coupon AS VARCHAR) FROM slots").fetchall()
    assert len(got) == len(tape)
    for loan_id, reason, down, up in got:
        assert (reason, down, up) == expected_slot(tape.loc[loan_id], cfg), loan_id


# =============================================================================
# Worked examples on hand-made loans
# =============================================================================

BASE_LOAN = {"loan_id": "LN00000001", "program": "Conventional", "product": "30Y Fixed",
             "dq_status": "Current", "note_rate": 6.0, "orig_upb": 400000, "state": "TX", "fico": 760}


@pytest.fixture(scope="module")
def rules() -> sl.SlottingRules:
    """The real rules, checked against the hand-made tape's columns."""
    return sl.load_slotting_rules(list(BASE_LOAN), PROGRAMS, PRODUCTS)


def slot_one(rules: sl.SlottingRules, **fields: Any) -> dict[str, Any]:
    """Run the one-pass SQL on a one-loan tape (BASE_LOAN with fields overridden).

    TECH: con.register makes a pandas DataFrame queryable as a DuckDB view; it is
      copied into a real `loans` table, the name slots_sql reads.
    """
    con = duckdb.connect()
    try:
        con.register("one_loan", pd.DataFrame([{**BASE_LOAN, **fields}]))
        con.execute("CREATE TABLE loans AS SELECT * FROM one_loan")
        sql, params = sl.slots_sql(rules, WORDS)
        result = con.execute(sql, params)
        return dict(zip([d[0] for d in result.description], result.fetchone()))
    finally:
        con.close()


@pytest.mark.parametrize("note, down, up", [
    (3.125, "2.5", "3.0"),   # 3.125 - 0.50 = 2.625 -> down 2.5 (the board's loan)
    (3.0, "2.5", "3.0"),     # 2.50 exactly on a step stays 2.5
    (2.875, "2.0", "2.5"),   # 2.375 rounds DOWN to 2.0, never to the nearest
    (6.999, "6.0", "6.5"),   # 6.499 still rounds down
    (7.0, "6.5", "7.0"),
])
def test_coupon_rule_worked_examples(rules: sl.SlottingRules, note: float, down: str, up: str) -> None:
    """BUSINESS: down = note rate - 0.50 strip, rounded DOWN to 0.5; up = down + 0.5.
      Rounding down keeps at least the minimum strip for servicing and the guarantee fee."""
    row = slot_one(rules, note_rate=note)
    assert (str(row["down_coupon"]), str(row["up_coupon"])) == (down, up)


@pytest.mark.parametrize("fields, reason", [
    ({"program": "Jumbo", "product": "7/6 ARM", "dq_status": "60"}, "no_agency"),
    ({"product": "7/6 ARM", "dq_status": "60"}, "product"),
    ({"dq_status": "30"}, "status"),
    ({"dq_status": "REO"}, "status"),
    ({"program": "Non-QM"}, "no_agency"),
    ({"program": "Non-QM", "product": "30Y Fixed IO"}, "no_agency"),
    ({}, None),
])
def test_the_first_failing_check_is_the_reason(rules: sl.SlottingRules, fields: dict[str, Any],
                                               reason: str | None) -> None:
    """BUSINESS: checks run agency, then product, then status; a Jumbo ARM that is
      60 days late is "no agency pool", so the totals never double count."""
    row = slot_one(rules, **fields)
    assert row["reason"] == reason and row["eligible"] is (reason is None)
    assert (row["down_coupon"] is None) is (reason is not None)


@pytest.mark.parametrize("program, agency", [("Conventional", "UMBS"), ("High-Balance", "UMBS"),
                                             ("FHA", "GNMA II"), ("VA", "GNMA II"), ("USDA", "GNMA II")])
def test_agency_map(rules: sl.SlottingRules, program: str, agency: str) -> None:
    """BUSINESS: conventional and High-Balance loans go to UMBS; FHA, VA, USDA to GNMA II."""
    assert slot_one(rules, program=program)["agency"] == agency


@pytest.mark.parametrize("fields, stories, text", [
    ({"orig_upb": 85000}, ["LLB_85K"], "LLB 85K"),        # on the cap: fits the tier
    ({"orig_upb": 85001}, ["LLB_110K"], "LLB 110K"),      # $1 over: the next tier only
    ({"orig_upb": 275001}, [], "Generic TBA"),            # above every tier
    ({"orig_upb": 60000, "state": "NY", "fico": 650}, ["LLB_85K", "NY", "LOW_FICO"], "LLB 85K, NY, Low FICO"),
    ({"state": "PR", "product": "15Y Fixed"}, ["PR"], "PR"),
    ({"fico": 700}, [], "Generic TBA"),                   # 700 is not below 700
    ({"orig_upb": 60000, "dq_status": "30"}, [], "Delinquent"),  # not slotted: no stories
])
def test_spec_stories(rules: sl.SlottingRules, fields: dict[str, Any], stories: list[str], text: str) -> None:
    """BUSINESS: LLB keeps only the lowest tier a loan fits; a loan can carry several
      stories; a loan that is not slotted carries none, and its Spec Stories cell
      shows the short reason instead."""
    row = slot_one(rules, **fields)
    assert row["stories"] == stories and row["spec_stories"] == text


# =============================================================================
# Config and words
# =============================================================================

def write_config(tmp_path: Path, old: str, new: str) -> Path:
    """A copy of slotting.toml with one piece of text replaced. TECH: checks it changed."""
    text = sl.SLOTTING_PATH.read_text(encoding="utf-8")
    assert old in text, old
    path = tmp_path / "slotting.toml"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return path


@pytest.mark.parametrize("old, new, message", [
    ('"GNMA II" = ["FHA", "VA", "USDA"]', '"GNMA II" = ["FHA", "VA", "USDA", "Jumbo"]', "two lists"),
    ('"GNMA II" = ["FHA", "VA", "USDA"]', '"GNMA II" = ["FHA", "VA"]', "missing ['USDA']"),
    ('"GNMA II" = ["FHA", "VA", "USDA"]', '"GNMA II" = ["FHA", "VA", "USDA", "RHS"]', "unknown ['RHS']"),
    ('"15Y Fixed" = "15Y"', '"15Y Fixed" = "15Y"\n"40Y Fixed" = "40Y"', "unknown ['40Y Fixed']"),
    ('"GNMA II" = ["FHA", "VA", "USDA"]', '"GNMA II" = []', "at least one program"),
    ('"15Y Fixed" = "15Y"', '"15Y Fixed" = ""', "each with a term label"),
    ("coupon_step_pct = 0.5", "coupon_step_pct = 0.5\nmax_spread_pct = 2.5", "keys must be"),
    ("coupon_step_pct = 0.5", "coupon_step_pct = 0", "above 0"),
    ("min_strip_pct = 0.50", "min_strip_pct = -0.25", "at least 0"),
    ("min_strip_pct = 0.50", 'min_strip_pct = "0.50"', "must be a number"),
    ('eligible = "Current"', 'eligible = ["Current", "30"]', "one MBA status"),
    # TECH: "\n[coupons]\n" is the section header line; the bare text also
    #   appears in the file's header comment, which must not be the one replaced.
    ("\n[coupons]\n", "\n[extra]\nx = 1\n\n[coupons]\n", "sections must be exactly"),
])
def test_bad_config_stops_the_app(tmp_path: Path, old: str, new: str, message: str) -> None:
    """BUSINESS: a typo in the rules must stop LoanIQ at start-up, never leave loans
      silently unslotted or in two pools."""
    path = write_config(tmp_path, old, new)
    with pytest.raises(ValueError, match=message.replace("[", r"\[").replace("]", r"\]")):
        sl.load_slotting_rules(list(BASE_LOAN), PROGRAMS, PRODUCTS, path=path)


def test_unknown_field_in_a_slot_template_is_refused(rules: sl.SlottingRules) -> None:
    """TECH: a {typo} in content/slotting.json's slot template fails loudly."""
    words = {**WORDS, "slot": {**WORDS["slot"], "slotted": "{agency} {coupon}"}}
    with pytest.raises(ValueError, match="unknown field"):
        sl.slots_sql(rules, words)


def test_words_cover_every_story_family_and_reason(rules: sl.SlottingRules) -> None:
    """BUSINESS: every story and every reason has visitor-facing words, so the screen
      never shows a raw config name or code."""
    assert set(rules.families()) <= set(WORDS["stories"])
    assert set(sl.REASONS) == set(WORDS["reasons"])
    assert all(WORDS["stories"][f].get("why") for f in rules.families())


def test_unsourced_rules_are_flagged_in_public_sources() -> None:
    """BUSINESS: every rule traces to a public source, or is flagged as having none:
      the GNMA II mapping, Non-QM and the 0.50 strip are flagged, and the agency
      eligibility row names the slotting config."""
    section = SOURCES.split("## Rules without a recorded source", 1)[1]
    for rule in ("GNMA II", "Non-QM", "0.50"):
        assert rule in section
    assert "slotting.toml" in SOURCES.split("## Rules without a recorded source", 1)[0]


# =============================================================================
# Timing
# =============================================================================

@pytest.fixture(scope="module")
def big_client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    """The app over a 50,000-loan tape (size from api.toml, fixed seed)."""
    folder = tmp_path_factory.mktemp("big_slot_tape")
    gen.write_tape(gen.generate_tape(n=PERF["timing_tape_loans"], seed=7), folder)
    with TestClient(main.create_app(folder)) as c:
        yield c


def test_a_run_is_fast_on_50k_loans(big_client: TestClient) -> None:
    """BUSINESS: slotting a large seller tape takes moments on the server; the screen,
      not the server, paces the commentary. Whole run under slotting_run_budget_ms
      (api.toml, illustrative), then a sorted, filtered grid page from the slotted
      tape still under page_budget_ms.
    TECH: the clock covers the full HTTP stream, every step to the done event."""
    start = time.perf_counter()
    events = run(big_client)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert events[-1][0] == "done" and events[-1][1]["totals"]["loans"] == PERF["timing_tape_loans"]
    assert elapsed_ms < PERF["slotting_run_budget_ms"], f"run took {elapsed_ms:.0f} ms"
    params = {"sort": "slot:desc", "filter": json.dumps(
        {"spec_stories": {"filterType": "text", "type": "contains", "filter": "LLB"}})}
    assert big_client.get("/api/loans", params=params).status_code == 200  # warm-up
    start = time.perf_counter()
    resp = big_client.get("/api/loans", params=params)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert resp.status_code == 200 and resp.json()["total"] > 0
    assert elapsed_ms < PERF["page_budget_ms"], f"page took {elapsed_ms:.0f} ms"
