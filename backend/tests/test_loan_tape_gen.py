"""Tests for the synthetic loan tape generator (backend/app/loan_tape_gen.py).

BUSINESS: every later screen trusts this tape. These tests protect the promises
  the desk relies on: the same seed always gives the same tape, balances and dates
  make sense, program rules hold (Jumbo above the limit, VA at most 100% LTV), the
  delinquency picture is realistic, and every coverage minimum is met.
TECH: pytest. A module-scoped fixture builds the default tape once (seed 42,
  2,000 loans) and shares it across tests. Minimum counts are read from the config,
  not copied here, so the config stays the one home of those numbers.
"""

from __future__ import annotations

import copy
import time
from decimal import Decimal, localcontext
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest

from app import loan_tape_gen as gen
from app.spec_stories import family, load_spec_stories

CFG = gen.load_config()
STORIES = load_spec_stories(gen.COLUMNS)
AS_OF = pd.Timestamp(CFG["run"]["as_of_default"])
SCHEMA_DOC = gen.REPO_ROOT / "docs" / "domain" / "loan-tape-schema.md"


@pytest.fixture(scope="module")
def tape() -> pd.DataFrame:
    """The default tape (config defaults: n, seed, as-of), built once per module.

    TECH: pytest fixtures are set-up functions; scope="module" means every test in
      this file gets the same DataFrame instead of regenerating it.
    """
    return gen.generate_tape()


def is_arm_row(df: pd.DataFrame) -> pd.Series:
    """True for adjustable-rate loans, by product name (5/6, 7/6, 10/6 ARM)."""
    return df["product"].str.contains("ARM")


# -----------------------------------------------------------------------------
# Repeatability and shape
# -----------------------------------------------------------------------------

def test_same_seed_gives_identical_tape(tape: pd.DataFrame) -> None:
    """BUSINESS: a demo must show the same loans every time it is rebuilt."""
    pd.testing.assert_frame_equal(tape, gen.generate_tape())


def test_different_seed_gives_different_tape(tape: pd.DataFrame) -> None:
    """BUSINESS: the seed really drives the tape (no hidden fixed data)."""
    other = gen.generate_tape(seed=CFG["run"]["seed_default"] + 1)
    assert not other["loan_id"].equals(tape["loan_id"])


def test_columns_and_row_count(tape: pd.DataFrame) -> None:
    """BUSINESS: the tape has exactly the published fields, one row per loan."""
    assert list(tape.columns) == gen.COLUMNS
    assert len(tape) == CFG["run"]["n_default"]


def test_loan_ids_are_unique_ln_plus_8_digits(tape: pd.DataFrame) -> None:
    """BUSINESS: the loan ID is the key the desk and seller both quote."""
    assert tape["loan_id"].is_unique
    assert tape["loan_id"].str.fullmatch(r"LN\d{8}").all()


def test_schema_doc_lists_every_column() -> None:
    """BUSINESS: every field on the tape is documented for a first-time reader.

    TECH: looks for each column as a backticked name in a table row of the doc.
    """
    doc = SCHEMA_DOC.read_text(encoding="utf-8")
    missing = [c for c in gen.COLUMNS if f"| `{c}` |" not in doc]
    assert missing == []


# -----------------------------------------------------------------------------
# Balances, rates and amortization
# -----------------------------------------------------------------------------

def test_current_upb_never_exceeds_orig_upb(tape: pd.DataFrame) -> None:
    """BUSINESS: amortizing loans pay down; none of these loans can grow."""
    assert (tape["current_upb"] <= tape["orig_upb"]).all()
    assert (tape["current_upb"] > 0).all()


def test_level_payment_textbook_example() -> None:
    """BUSINESS: $200,000 at 6.000% for 360 months is $1,199.10 a month."""
    pay = gen.level_payment(np.array([200_000.0]), np.array([6.0]), np.array([360]))
    assert round(float(pay[0]), 2) == 1199.10


def exact_balance(upb: float, rate_pct: float, payment: float, k: int) -> Decimal:
    """Month-by-month schedule in exact Decimal arithmetic: B = B + B x r - P.

    TECH: localcontext(prec=50) keeps 50 significant digits, so this is the
      reference the float closed-form formula is checked against.
    """
    with localcontext() as ctx:
        ctx.prec = 50
        r = Decimal(str(rate_pct)) / Decimal(1200)
        bal, pay = Decimal(str(upb)), Decimal(str(payment))
        for _ in range(k):
            bal = bal + bal * r - pay
        return bal


def test_amortization_matches_exact_decimal_schedule(tape: pd.DataFrame) -> None:
    """BUSINESS: current UPB is right to the penny for current, amortizing loans.

    TECH: float64 closed form vs. a 50-digit Decimal loop, on 60 loans.
      Allowed gap: half a cent of rounding plus float noise.
    """
    sample = tape[(tape["dq_status"] == "Current") & ~tape["product"].str.contains("IO")
                  & (tape["loan_age"] > 0)].head(60)
    for row in sample.itertuples():
        expected = exact_balance(row.orig_upb, row.note_rate, row.pi_payment, row.loan_age)
        assert abs(Decimal(str(row.current_upb)) - expected) <= Decimal("0.006")


def test_delinquent_balance_stops_at_last_paid_installment(tape: pd.DataFrame) -> None:
    """BUSINESS: a loan 30 days late has made one fewer payment than its age."""
    sample = tape[(tape["dq_status"] == "30") & ~tape["product"].str.contains("IO")].head(20)
    assert len(sample) > 0
    for row in sample.itertuples():
        expected = exact_balance(row.orig_upb, row.note_rate, row.pi_payment, row.loan_age - 1)
        assert abs(Decimal(str(row.current_upb)) - expected) <= Decimal("0.006")


def test_interest_only_loans_pay_interest_only(tape: pd.DataFrame) -> None:
    """BUSINESS: during the IO period the balance does not fall and the payment is
    balance x rate / 12."""
    io = tape[tape["product"].str.contains("IO") & (tape["loan_age"] < 120)]
    assert len(io) > 0
    assert (io["current_upb"] == io["orig_upb"]).all()
    expected = (io["orig_upb"] * io["note_rate"] / 1200).round(2)
    assert np.allclose(io["pi_payment"], expected, atol=0.005)


def test_note_rates_in_eighths_and_follow_vintage(tape: pd.DataFrame) -> None:
    """BUSINESS: lenders quote in 1/8ths, and 2023 loans carry far higher rates than
    2021 loans (the market base rate went from about 3% to over 6%)."""
    assert np.allclose((tape["note_rate"] / 0.125).round(), tape["note_rate"] / 0.125)
    year = tape["orig_date"].dt.year
    assert tape.loc[year == 2023, "note_rate"].mean() > tape.loc[year == 2021, "note_rate"].mean() + 2


def test_note_rates_follow_the_month_within_2022(tape: pd.DataFrame) -> None:
    """BUSINESS: rates move within a year. 2022 loans closed in Oct-Dec (base rate
    about 6%) carry clearly higher rates than loans closed in Jan-Mar (about 3.5%).

    TECH: compares 30-year fixed loans only, so the product mix cannot explain it.
    """
    fixed30 = tape[(tape["product"] == "30Y Fixed") & (tape["orig_date"].dt.year == 2022)]
    quarter = fixed30["orig_date"].dt.quarter
    early, late = fixed30.loc[quarter == 1, "note_rate"], fixed30.loc[quarter == 4, "note_rate"]
    assert len(early) > 5 and len(late) > 5
    assert late.mean() > early.mean() + 1.5


def test_rejects_rate_row_without_12_months() -> None:
    """TECH: every year of base rates must list all 12 months, January first."""
    cfg = copy.deepcopy(CFG)
    cfg["rates"]["base_rate_30y_by_month"]["2020"] = [3.0] * 11
    with pytest.raises(ValueError, match="12 monthly values"):
        gen.generate_tape(cfg=cfg)


# -----------------------------------------------------------------------------
# Dates and terms
# -----------------------------------------------------------------------------

def test_dates_are_in_order(tape: pd.DataFrame) -> None:
    """BUSINESS: a loan closes, then pays, then matures, all before or after the
    cut-off as appropriate."""
    assert (tape["orig_date"] < tape["first_pay_date"]).all()
    assert (tape["first_pay_date"] < tape["maturity_date"]).all()
    assert (tape["orig_date"] < AS_OF).all()
    assert (tape["orig_date"].dt.year >= CFG["vintage"]["first_year"]).all()


def test_payment_dates_fall_on_the_first(tape: pd.DataFrame) -> None:
    """BUSINESS: mortgage payments are due on the 1st of the month."""
    for col in ("first_pay_date", "maturity_date"):
        assert (tape[col].dt.day == 1).all()


def test_terms_add_up(tape: pd.DataFrame) -> None:
    """BUSINESS: remaining term = original term - payments already due."""
    assert (tape["remaining_term"] == tape["orig_term"] - tape["loan_age"]).all()
    assert (tape["loan_age"] >= 0).all()
    months = ((tape["maturity_date"].dt.year - tape["first_pay_date"].dt.year) * 12
              + tape["maturity_date"].dt.month - tape["first_pay_date"].dt.month + 1)
    assert (months == tape["orig_term"]).all()


# -----------------------------------------------------------------------------
# Program rules and LTV family
# -----------------------------------------------------------------------------

def test_program_rules(tape: pd.DataFrame) -> None:
    """BUSINESS: the program definitions the desk slots on must hold."""
    by = tape.groupby("program")
    assert tape.loc[tape["program"] == "Jumbo", "orig_upb"].min() > CFG["limits"]["jumbo_floor"]
    assert tape.loc[tape["program"] == "VA", "ltv"].max() <= 100
    assert by["fico"].mean()["FHA"] < by["fico"].mean()["Conventional"]
    assert set(tape.loc[tape["product"] == "30Y Fixed IO", "program"]) == {"Non-QM"}
    assert set(tape.loc[tape["program"] == "USDA", "product"]) == {"30Y Fixed"}
    gov = tape["program"].isin(["FHA", "VA", "USDA"])
    assert (tape.loc[gov, "occupancy"] == "Primary").all()


def test_loan_limits_by_vintage(tape: pd.DataFrame) -> None:
    """BUSINESS: conforming loans fit under their year's FHFA baseline; High-Balance
    sits above the baseline and at or under the 150% ceiling."""
    base = tape["orig_date"].dt.year.astype(str).map(CFG["limits"]["baseline_by_year"])
    conf = tape["program"].isin(["Conventional", "FHA", "VA", "USDA"])
    assert (tape.loc[conf, "orig_upb"] <= base[conf]).all()
    hb = tape["program"] == "High-Balance"
    assert (tape.loc[hb, "orig_upb"] > base[hb]).all()
    assert (tape.loc[hb, "orig_upb"] <= base[hb] * CFG["limits"]["high_cost_multiple"]).all()


def test_ltv_family_is_consistent(tape: pd.DataFrame) -> None:
    """BUSINESS: LTV <= CLTV <= HCLTV (seconds and full HELOC lines only add), and
    MTM LTV = current UPB / current value."""
    assert (tape["ltv"] <= tape["cltv"]).all() and (tape["cltv"] <= tape["hcltv"]).all()
    assert np.allclose(tape["ltv"], tape["orig_upb"] / tape["appraised_value"] * 100, atol=0.006)
    assert np.allclose(tape["mtm_ltv"], tape["current_upb"] / tape["current_value"] * 100, atol=0.006)


def test_arm_fields_present_only_for_arms(tape: pd.DataFrame) -> None:
    """BUSINESS: ARM details are blank on fixed loans; ARMs are 2021+ SOFR loans."""
    arm_cols = ["arm_index", "margin", "first_reset_date", "initial_cap", "periodic_cap",
                "lifetime_cap"]
    arm = is_arm_row(tape)
    assert tape.loc[~arm, arm_cols].isna().all().all()
    assert tape.loc[arm, arm_cols].notna().all().all()
    assert (tape.loc[arm, "orig_date"].dt.year >= CFG["arm"]["first_year"]).all()
    assert (tape.loc[arm, "first_reset_date"] > tape.loc[arm, "first_pay_date"]).all()


# -----------------------------------------------------------------------------
# Delinquency
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("seed", [42, 7, 2026])
def test_delinquency_rate_near_target(seed: int) -> None:
    """BUSINESS: about 7% of loans are delinquent (any status other than Current).

    TECH: random draws vary by seed, so allow +/- 1.5 percentage points.
    """
    df = gen.generate_tape(seed=seed)
    rate = (df["dq_status"] != "Current").mean()
    assert abs(rate - CFG["delinquency"]["target_rate"]) <= 0.015


def test_riskier_loans_are_more_delinquent(tape: pd.DataFrame) -> None:
    """BUSINESS: the logistic score works: low-FICO loans go bad more often."""
    dq = tape["dq_status"] != "Current"
    assert dq[tape["fico"] < 680].mean() > 2 * dq[tape["fico"] >= 760].mean()


def test_pay_history_ends_consistent_with_status(tape: pd.DataFrame) -> None:
    """BUSINESS: the latest month in the pay history agrees with today's status;
    a loan with no payment due yet shows "-"."""
    assert (tape["pay_history_12m"].str.len() == 12).all()
    last = tape["pay_history_12m"].str[-1]
    expected = tape["dq_status"].map(gen.HISTORY_CODE)
    no_payment_yet = tape["loan_age"] == 0
    assert ((last == expected) | (no_payment_yet & (last == "-"))).all()


def test_pay_history_rolls_one_bucket_per_month(tape: pd.DataFrame) -> None:
    """BUSINESS: a loan cannot skip a bucket: each month's missed count rises by at
    most one (current -> 30 -> 60 ...)."""
    for hist in tape["pay_history_12m"]:
        digits = [int(c) for c in hist if c.isdigit()]
        assert all(b - a <= 1 for a, b in zip(digits, digits[1:])), hist


def test_days_past_due_match_mba_buckets(tape: pd.DataFrame) -> None:
    """BUSINESS: MBA buckets: 30 = 30-59 days, 60 = 60-89, 90 = 90-119, 120+ = 120+."""
    ranges = {"Current": (0, 0), "30": (30, 59), "60": (60, 89), "90": (90, 119),
              "120+": (120, 10_000), "FC": (120, 10_000), "REO": (180, 10_000)}
    for status, (lo, hi) in ranges.items():
        dpd = tape.loc[tape["dq_status"] == status, "days_past_due"]
        assert dpd.between(lo, hi).all(), status


# -----------------------------------------------------------------------------
# Coverage minimums (counts read from the config)
# -----------------------------------------------------------------------------

def test_coverage_high_ltv(tape: pd.DataFrame) -> None:
    """BUSINESS: enough LTV > 125 loans to show high-LTV refinance stories."""
    assert (tape["ltv"] > 125).sum() >= CFG["coverage"]["high_ltv"]["count"]


def test_coverage_llb_tiers(tape: pd.DataFrame) -> None:
    """BUSINESS: every low-loan-balance band (between consecutive tier caps in
    spec_stories.toml) has the minimum number of loans, on eligible products."""
    tiers = family(STORIES, "LLB")
    minimum = CFG["coverage"]["stories"]["LLB"]
    lows = [0.0] + [s.cap for s in tiers[:-1]]
    for story, low in zip(tiers, lows):
        in_band = (tape["product"].isin(story.products)
                   & tape["orig_upb"].between(low, story.cap, inclusive="right"))
        assert in_band.sum() >= minimum, story.name


def test_coverage_states(tape: pd.DataFrame) -> None:
    """BUSINESS: enough New York and Puerto Rico loans for geographic stories."""
    for name in ("NY", "PR"):
        story = family(STORIES, name)[0]
        hits = tape["product"].isin(story.products) & (tape["state"] == name)
        assert hits.sum() >= CFG["coverage"]["stories"][name], name


def test_coverage_arm_resets(tape: pd.DataFrame) -> None:
    """BUSINESS: enough ARMs with a first reset inside the next 6 months."""
    spec = CFG["coverage"]["arm_reset"]
    end = AS_OF + pd.DateOffset(months=spec["window_months"])
    soon = tape["first_reset_date"].between(AS_OF, end, inclusive="left")
    assert soon.sum() >= spec["count"]


def test_coverage_serious_delinquency(tape: pd.DataFrame) -> None:
    """BUSINESS: enough 90+, FC and REO loans to show distressed-loan handling."""
    for rule in CFG["coverage"]["delinquency"]:
        assert tape["dq_status"].isin(rule["statuses"]).sum() >= rule["count"], rule["label"]


# -----------------------------------------------------------------------------
# Inputs, command line and files
# -----------------------------------------------------------------------------

def test_rejects_tape_too_small_for_coverage() -> None:
    """BUSINESS: a tiny tape cannot hold every minimum, so it is refused."""
    with pytest.raises(ValueError, match="at least"):
        gen.generate_tape(n=CFG["run"]["min_n"] - 1)


def test_rejects_mid_month_as_of() -> None:
    """BUSINESS: tapes are cut at a month boundary."""
    with pytest.raises(ValueError, match="1st of a month"):
        gen.generate_tape(as_of="2026-11-18")


def test_rejects_as_of_year_missing_from_config() -> None:
    """TECH: no rate, limit or HPI row for the year means the tape cannot be priced."""
    with pytest.raises(ValueError, match="no 2031 row"):
        gen.generate_tape(as_of="2031-01-01")


def test_choose_refuses_when_too_few_candidates() -> None:
    """TECH: coverage forcing fails loudly instead of silently under-filling."""
    rng = np.random.default_rng(0)
    with pytest.raises(ValueError, match="need 3, have 1"):
        gen.choose(rng, np.array([True, False]), 3, "test")


def test_cli_defaults_write_parquet_and_csv(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """BUSINESS: `python -m app.loan_tape_gen` with no options writes the default tape.

    TECH: tmp_path is a pytest fixture giving an empty temp folder; capsys captures
      printed output. Money must round-trip as exact Decimal(14,2).
    """
    assert gen.main(["--out-dir", str(tmp_path)]) == 0
    table = pq.read_table(tmp_path / "loan_tape.parquet")
    assert table.num_rows == CFG["run"]["n_default"]
    assert str(table.schema.field("current_upb").type) == "decimal128(14, 2)"
    csv = pd.read_csv(tmp_path / "loan_tape.csv")
    assert len(csv) == table.num_rows and list(csv.columns) == gen.COLUMNS
    assert f"Wrote {table.num_rows:,} loans" in capsys.readouterr().out


def test_generation_is_fast() -> None:
    """TECH: generation is vectorized; 50,000 loans should take well under 10 s
    (about 0.7 s on a laptop). Protects against slow per-loan loops creeping in."""
    start = time.perf_counter()
    gen.generate_tape(n=50_000)
    assert time.perf_counter() - start < 10
