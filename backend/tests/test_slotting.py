"""Tests for product slotting (app/slotting.py, app/slotting_api.py, config/slotting.toml).

BUSINESS: what a desk relies on before it prices a tape: every loan gets exactly one
  slot; a loan that is behind, modified or in forbearance never reaches an agency
  pool; government loans go to Ginnie Mae II and conventional loans to UMBS; the
  pass-through coupons follow the formula to the basis point, including its edges;
  spec stories show the tightest low-balance tier; and a bad rule stops the app
  instead of mis-slotting loans. The rules popup shows exactly what the engine ran.
TECH: pytest. Worked examples run the real SQL on a small Parquet tape built from
  one real loan with fields overridden, so each case is one line. The default tape's
  slots are checked against an independent pandas reading of the same rules. Config
  errors are tested by writing a changed copy of slotting.toml to a temp folder.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator

import duckdb
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import loan_tape_gen as gen
from app import main
from app import slotting as sl
from app.agent.tape_db import close_readonly_tape, open_readonly_tape
from tests.agent_fixtures import loan_store, tape_dir  # noqa: F401

REPO = Path(__file__).resolve().parents[2]
SOURCES = (REPO / "docs" / "public-sources.md").read_text(encoding="utf-8")


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(scope="module")
def tape(tape_dir: Path) -> pd.DataFrame:  # noqa: F811
    """The seeded default tape, read independently with pandas."""
    return pd.read_parquet(tape_dir / main.TAPE_FILE)


@pytest.fixture(scope="module")
def slotted(loan_store: main.LoanStore) -> pd.DataFrame:  # noqa: F811
    """The grid's slotted `loans` table, as the API serves it."""
    return loan_store.con.execute("SELECT * FROM loans").df()


@pytest.fixture(scope="module")
def client(tape_dir: Path) -> Iterator[TestClient]:  # noqa: F811
    """The whole app over the seeded tape."""
    with TestClient(main.create_app(tape_dir)) as c:
        yield c


def slot_loans(tmp_path: Path, template: pd.DataFrame, rows: list[dict[str, Any]],
               rules: sl.SlottingRules | None = None) -> list[dict[str, Any]]:
    """Slot hand-made loans: each row overrides fields of one real loan.

    TECH: writes a Parquet file, runs create_slotted_table on it, returns the
      slot columns per loan in row order. Rules default to the real config.
    """
    base = template.iloc[0].to_dict()
    df = pd.DataFrame([{**base, "loan_id": f"T{i}", **row} for i, row in enumerate(rows)])
    path = tmp_path / "t.parquet"
    df.astype(template.dtypes.to_dict()).to_parquet(path, index=False)
    con = duckdb.connect()
    try:
        sl.create_slotted_table(con, path, rules or sl.load_slotting_rules(list(template.columns)))
        out = con.execute(f"SELECT {', '.join(sl.SLOT_COLUMNS)} FROM loans ORDER BY loan_id").df()
    finally:
        con.close()
    return out.to_dict("records")


CLEAN = {"dq_status": "Current", "mod_flag": False, "forbearance_flag": False, "ltv": 80.0,
         "orig_upb": 400000.0, "state": "CA", "fico": 760, "product": "30Y Fixed"}


def num(value: Any) -> Decimal | None:
    """A DECIMAL column value as Decimal, or None for NULL (pandas gives NaN or None)."""
    return None if value is None or pd.isna(value) else Decimal(str(value))


# =============================================================================
# The coupon formula, worked examples
# =============================================================================

# BUSINESS: UMBS: min spread 75 bps (25 servicing + 50 guarantee fee), max 250 bps,
#   up coupon down to a 50 bps spread (25 bps buy-down). Ginnie Mae II: 25 to 75
#   bps, no buy-down. Coupons in half points. Every number illustrative.
@pytest.mark.parametrize("program, note, net, base, down, up", [
    # UMBS, note 6.875: net 6.125 -> base 6.0; down 5.5 (spread 1.375 ok); up 6.5 (0.375 < 0.50)
    ("Conventional", 6.875, "6.125", "6.0", "5.5", None),
    # net exactly on a coupon: note 6.25 -> net 5.5 = base; up 6.0 is only 0.25 above
    ("Conventional", 6.25, "5.5", "5.5", "5.0", None),
    # up coupon exactly at the 0.50 floor is allowed: note 7.0 -> base 6.0, up 6.5
    ("Conventional", 7.0, "6.25", "6.0", "5.5", "6.5"),
    ("High-Balance", 6.5, "5.75", "5.5", "5.0", "6.0"),
    # Ginnie Mae II: down coupon exactly at the 0.75 maximum is allowed
    ("FHA", 6.75, "6.5", "6.5", "6.0", None),
    # ... and one 1/8 above is not: spread 0.875 > 0.75
    ("VA", 6.875, "6.625", "6.5", None, None),
    ("USDA", 3.125, "2.875", "2.5", None, None),
])
def test_coupon_formula(tmp_path: Path, tape: pd.DataFrame, program: str, note: float, net: str,
                        base: str, down: str | None, up: str | None) -> None:
    """BUSINESS: net rate = note - min spread; base = highest half point at or below it;
    down and up one step each side, only inside the execution's spread limits."""
    [row] = slot_loans(tmp_path, tape, [{**CLEAN, "program": program, "note_rate": note}])
    assert row["slot_status"] == sl.AGENCY
    assert num(row["net_rate"]) == Decimal(net) and num(row["base_coupon"]) == Decimal(base)
    assert num(row["down_coupon"]) == (Decimal(down) if down else None)
    assert num(row["up_coupon"]) == (Decimal(up) if up else None)


def test_coupon_spreads_hold_on_every_loan(slotted: pd.DataFrame) -> None:
    """BUSINESS: on the whole tape, each offered coupon keeps its spread inside the
    execution's limits, in bps: UMBS base 75-125, down <= 250, up >= 50; Ginnie
    base 25-75, down <= 75, never an up coupon."""
    tba = slotted[slotted["base_coupon"].notna()]
    spread = lambda col: (tba["note_rate"] - tba[col].astype(float)) * 100  # noqa: E731
    umbs, g2 = tba["execution"] == "UMBS", tba["execution"] == "Ginnie Mae II"
    assert spread("base_coupon")[umbs].between(75, 124.99).all()
    assert spread("base_coupon")[g2].between(25, 74.99).all()
    assert (spread("down_coupon")[umbs].dropna() <= 250).all()
    assert (spread("down_coupon")[g2].dropna() <= 75).all()
    assert (spread("up_coupon")[umbs].dropna() >= 50).all()
    assert tba.loc[g2, "up_coupon"].isna().all()
    assert (tba["base_coupon"].astype(float) * 2 % 1 == 0).all(), "half-point coupons only"


# =============================================================================
# Statuses, executions, products and stories
# =============================================================================

@pytest.mark.parametrize("change, status, reason, execution, product", [
    ({"program": "Conventional"}, "Agency", None, "UMBS", "UMBS 30"),
    ({"program": "Conventional", "product": "20Y Fixed"}, "Agency", None, "UMBS", "UMBS 20"),
    ({"program": "Conventional", "product": "15Y Fixed"}, "Agency", None, "UMBS", "UMBS 15"),
    ({"program": "High-Balance"}, "Agency", None, "UMBS", "UMBS 30 High-Balance"),
    ({"program": "High-Balance", "product": "5/6 ARM"}, "Agency", None, "UMBS", "UMBS ARM"),
    ({"program": "Conventional", "ltv": 130.5}, "Agency", None, "UMBS", "UMBS High-LTV"),
    ({"program": "FHA"}, "Agency", None, "Ginnie Mae II", "G2 30"),
    ({"program": "VA", "product": "15Y Fixed"}, "Agency", None, "Ginnie Mae II", "G2 15"),
    ({"program": "Jumbo"}, "Whole loan", None, "Whole loan", None),
    ({"program": "Non-QM", "product": "30Y Fixed IO"}, "Whole loan", None, "Whole loan", None),
    # not-deliverable rules come first, whatever the program; the first match is the reason
    ({"program": "Jumbo", "dq_status": "90"}, "Not deliverable", "Delinquent", None, None),
    ({"program": "FHA", "mod_flag": True, "forbearance_flag": True}, "Not deliverable", "Modified", None, None),
    ({"program": "Conventional", "forbearance_flag": True}, "Not deliverable", "Forbearance", None, None),
    # no Ginnie product for a 20-year loan: flagged as a config gap, not guessed
    ({"program": "FHA", "product": "20Y Fixed"}, "Unslotted", "No product rule", None, None),
])
def test_status_execution_and_product(tmp_path: Path, tape: pd.DataFrame, change: dict[str, Any],
                                      status: str, reason: str | None, execution: str | None,
                                      product: str | None) -> None:
    """BUSINESS: each loan lands in exactly one slot, by the rules' order."""
    [row] = slot_loans(tmp_path, tape, [{**CLEAN, "note_rate": 6.5, **change}])
    assert (row["slot_status"], row["slot_reason"], row["execution"], row["slot_product"]) == \
        (status, reason, execution, product)
    if status != "Agency" or product in ("UMBS ARM", "UMBS High-LTV"):
        assert row["base_coupon"] is None or pd.isna(row["base_coupon"]), "no TBA coupon"
        assert row["spec_stories"] is None


@pytest.mark.parametrize("change, stories", [
    ({"orig_upb": 80000.0, "state": "NY", "fico": 650}, "LLB_85K, NY, LOW_FICO"),
    ({"orig_upb": 140000.0}, "LLB_150K"),          # the tightest tier the loan fits
    ({"orig_upb": 150000.0}, "LLB_150K"),          # caps are inclusive
    ({"state": "PR"}, "PR"),
    ({}, None),                                     # no story
    ({"orig_upb": 80000.0, "product": "7/6 ARM"}, None),   # stories are for TBA products only
])
def test_spec_stories(tmp_path: Path, tape: pd.DataFrame, change: dict[str, Any], stories: str | None) -> None:
    """BUSINESS: a TBA agency loan shows every story it carries, and only the
    tightest low-loan-balance tier, the one a desk quotes first."""
    [row] = slot_loans(tmp_path, tape, [{**CLEAN, "program": "Conventional", "note_rate": 6.5, **change}])
    assert row["spec_stories"] == stories


def test_default_tape_matches_an_independent_reading(tape: pd.DataFrame, slotted: pd.DataFrame) -> None:
    """BUSINESS: on the real tape every loan is slotted (no config gaps), and the
    statuses agree with the rules read by hand: not current, modified or in
    forbearance -> Not deliverable; Jumbo and Non-QM -> Whole loan; the rest Agency."""
    bad = (tape["dq_status"] != "Current") | tape["mod_flag"] | tape["forbearance_flag"]
    whole = tape["program"].isin(["Jumbo", "Non-QM"])
    expected = pd.Series("Agency", index=tape.index).mask(whole, "Whole loan").mask(bad, "Not deliverable")
    got = slotted.set_index("loan_id").loc[tape["loan_id"], "slot_status"].to_numpy()
    assert (got == expected.to_numpy()).all()
    assert (slotted["slot_status"] != sl.UNSLOTTED).all()
    gov = slotted["program"].isin(["FHA", "VA", "USDA"]) & (slotted["slot_status"] == "Agency")
    assert (slotted.loc[gov, "execution"] == "Ginnie Mae II").all()


def test_slotting_keeps_every_tape_column_and_loan(tape: pd.DataFrame, slotted: pd.DataFrame) -> None:
    """TECH: the slotted table is the tape plus SLOT_COLUMNS, same loans, same order."""
    assert list(slotted.columns) == list(tape.columns) + sl.SLOT_COLUMNS
    assert slotted["loan_id"].tolist() == tape["loan_id"].tolist()


def test_agent_copy_is_slotted_like_the_grid(tape_dir: Path, slotted: pd.DataFrame) -> None:  # noqa: F811
    """BUSINESS: Ask the Tape answers about slots with the same numbers the grid shows."""
    ro = open_readonly_tape(tape_dir / main.TAPE_FILE)
    try:
        theirs = ro.con.execute("SELECT loan_id, slot_product, base_coupon, spec_stories FROM loans "
                                "ORDER BY loan_id").df()
    finally:
        close_readonly_tape(ro)
    ours = slotted[["loan_id", "slot_product", "base_coupon", "spec_stories"]].sort_values("loan_id")
    pd.testing.assert_frame_equal(theirs.reset_index(drop=True), ours.reset_index(drop=True))


# =============================================================================
# Config checks: a bad rule stops the app
# =============================================================================

def broken(tmp_path: Path, old: str, new: str) -> Path:
    """A copy of slotting.toml with one piece of text changed."""
    text = sl.SLOTTING_PATH.read_text(encoding="utf-8")
    assert old in text, old
    path = tmp_path / "slotting.toml"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return path


@pytest.mark.parametrize("old, new, message", [
    ("where = \"dq_status <> 'Current'\"", "where = \"dq_status <> 'Current'; DROP TABLE loans\"",
     "semicolons"),
    ("where = \"dq_status <> 'Current'\"", "where = \"lower(dq_status) <> 'current'\"", "not allowed"),
    ("where = \"mod_flag = TRUE\"", "where = \"modified = TRUE\"", "unknown column"),
    ('pricing = "whole_loan"', 'pricing = "auction"', "pricing must be one of"),
    ('execution = "Ginnie Mae II"\nwhere = "product = \'30Y Fixed\'"',
     'execution = "Whole loan"\nwhere = "product = \'30Y Fixed\'"', "not a pass-through execution"),
    ("max_spread_bps = 75", "max_spread_bps = 74", "max_spread_bps must be at least"),
    ("guarantee_fee_bps = 50", "guarantee_fee_bps = -5", "must be a number of bps"),
    ('name = "UMBS 20"', 'name = "UMBS 15"', "duplicate rule names"),
    # TECH: "\ntba = true\n" is a rule line; the bare text also appears in a comment
    ("\ntba = true\n", '\ntba = "yes"\n', "tba must be true or false"),
    ('reason = "Modified"', 'reason = "Modified"\nseverity = 1', "unknown ['severity']"),
    ("coupon_step_pct = 0.5", "coupon_step_pct = 0", "coupon_step_pct must be above 0"),
])
def test_bad_rules_are_refused(tmp_path: Path, tape: pd.DataFrame, old: str, new: str, message: str) -> None:
    """BUSINESS: a typo or an unsafe rule must stop the app loudly, naming the problem,
    rather than mis-slot loans. TECH: rules are checked like the spec stories."""
    with pytest.raises(ValueError) as err:
        sl.load_slotting_rules(list(tape.columns), path=broken(tmp_path, old, new))
    assert message in str(err.value)


def test_every_rule_names_a_listed_public_source() -> None:
    """BUSINESS: each slotting rule traces to a source in docs/public-sources.md."""
    rules = sl.load_slotting_rules(gen.COLUMNS)
    names = ([r.source for r in rules.not_deliverable] + [e.source for e in rules.executions]
             + [e.fee_source for e in rules.executions if e.fee_source] + [p.source for p in rules.products])
    assert [n for n in names if n not in SOURCES] == []


def test_content_covers_exactly_the_slot_columns_and_rules() -> None:
    """BUSINESS: every slot column has a header and a glossary term that exists, and
    every rule has its plain-English line in content/slotting.json, with none stale."""
    words = json.loads(sl.CONTENT_PATH.read_text(encoding="utf-8"))
    glossary = {t["term"] for t in json.loads((REPO / "content" / "glossary.json").read_text(encoding="utf-8"))}
    rules = sl.load_slotting_rules(gen.COLUMNS)
    names = ([r.reason for r in rules.not_deliverable] + [e.name for e in rules.executions]
             + [p.name for p in rules.products])
    assert list(words["labels"]) == sl.SLOT_COLUMNS and list(words["terms"]) == sl.SLOT_COLUMNS
    assert set(words["terms"].values()) <= glossary
    assert sorted(words["rules"]) == sorted(names)


# =============================================================================
# The API
# =============================================================================

def test_rules_endpoint_shows_what_the_engine_runs(client: TestClient) -> None:
    """BUSINESS: the read-only rules popup shows the rules in force, in order, with
    their fees in bps and their sources, and says they are illustrative."""
    body = client.get("/api/slotting/rules").json()
    rules = sl.load_slotting_rules(gen.COLUMNS)
    assert body["illustrative"] is True and body["coupon_step_pct"] == 0.5
    assert [r["reason"] for r in body["not_deliverable"]] == ["Delinquent", "Modified", "Forbearance"]
    umbs = body["executions"][0]
    assert (umbs["name"], umbs["min_spread_bps"], umbs["max_spread_bps"]) == ("UMBS", 75.0, 250.0)
    assert [p["name"] for p in body["products"]] == [p.name for p in rules.products]
    assert "LLB_85K" in [s["name"] for s in body["spec_stories"]]
    assert body["not_deliverable"][0]["where"] == "dq_status <> 'Current'"


def test_slotting_summary_adds_up_to_the_grid(client: TestClient) -> None:
    """BUSINESS: the slotting panel accounts for every loan and dollar the grid shows,
    with not-deliverable loans listed by reason."""
    body = client.get("/api/loans/slotting").json()
    summary = client.get("/api/loans/summary").json()
    assert body["loans"] == summary["loan_count"] == sum(g["loans"] for g in body["groups"])
    assert body["current_upb"] == pytest.approx(summary["total_current_upb"], abs=0.01)
    statuses = [g["slot_status"] for g in body["groups"]]
    assert statuses == sorted(statuses, key=sl.STATUS_ORDER.index), "desk order: Agency first"
    reasons = {g["slot_reason"] for g in body["groups"] if g["slot_status"] == "Not deliverable"}
    assert reasons == {"Delinquent", "Modified", "Forbearance"}


def test_slotting_summary_follows_the_grid_filter_and_question(client: TestClient) -> None:
    """BUSINESS: slot the loans on screen: the same column filter and desk question as
    the grid, and the grid can itself filter on a slot column."""
    flt = json.dumps({"slot_product": {"filterType": "text", "type": "equals", "filter": "UMBS 30"}})
    body = client.get("/api/loans/slotting", params={"filter": flt}).json()
    page = client.get("/api/loans", params={"filter": flt, "limit": 1}).json()
    assert body["loans"] == page["total"] > 0
    assert {g["slot_product"] for g in body["groups"]} == {"UMBS 30"}
    hi = client.get("/api/loans/slotting", params={"question": "ltv_over_125"}).json()
    assert {g["slot_product"] for g in hi["groups"] if g["slot_status"] == "Agency"} <= {"UMBS High-LTV"}


@pytest.mark.parametrize("params", [{"filter": "{not json"}, {"question": "no_such_question"},
                                    {"filter": json.dumps({"x; DROP": {"filterType": "text",
                                                                        "type": "equals", "filter": "a"}})}])
def test_slotting_summary_refuses_bad_requests(client: TestClient, params: dict[str, str]) -> None:
    """BUSINESS: nothing typed into the request can change the SQL: a bad filter,
    an unknown question or an unknown column is a 400, as on /api/loans."""
    assert client.get("/api/loans/slotting", params=params).status_code == 400


def test_tape_line_still_counts_only_the_tapes_own_fields(client: TestClient) -> None:
    """BUSINESS: "41 fields" describes the seller's tape; slot columns are LoanIQ's."""
    assert client.get("/api/tape").json()["fields"] == len(gen.COLUMNS)


def test_slotting_routes_need_loaded_rules(loan_store: main.LoanStore) -> None:  # noqa: F811
    """TECH: a hand-built store without slotting answers 503, not a server error."""
    bare = main.LoanStore(con=loan_store.con, columns=loan_store.columns)
    with pytest.raises(main.HTTPException) as err:
        main.loaded_rules(bare)
    assert err.value.status_code == 503
