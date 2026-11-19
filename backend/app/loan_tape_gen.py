"""Synthetic loan tape generator: the first link in the LoanIQ flow.

Where it sits:
    [loan_tape_gen] -> data/loan_tape.parquet -> DuckDB -> loan API -> grid
    -> slotting -> best execution -> positions and optimizer -> pool candidates

BUSINESS:
    A loan tape is the spreadsheet a seller sends the capital markets desk: one row
    per loan with its program, balance, rate, borrower credit, collateral and
    payment status. Every later LoanIQ screen works from this tape, so it has to
    look like a real one: FHA borrowers have lower FICO than Jumbo borrowers, rates
    follow the year the loan was made, and riskier loans are more often delinquent.
    It also guarantees a minimum number of "story" loans (low balance, New York,
    Puerto Rico, LTV above 125, ARMs about to reset, serious delinquency) so every
    screen has something to show. All data is synthetic; all numbers illustrative.

TECH:
    Run from backend/:  python -m app.loan_tape_gen [--n 2000] [--seed 42]
                                                    [--as-of 2026-11-01] [--out-dir ..]
    Six-step pipeline, in this order (docs/domain/loan-tape-schema.md has the diagram):
      1. load config      every number comes from app/config/loan_tape_gen.toml; the
                          spec-story rules (LLB tiers, NY, PR) from spec_stories.toml
      2. sample drivers   the loan's "inputs": program, dates, credit, balance, collateral
      3. force coverage   edit drivers of a few loans so every minimum is met
      4. derive           rate, dates, payment, LTV family, ARM fields from the drivers
      5. delinquency      logistic score -> status -> pay history -> current balance
      6. write            Parquet (exact Decimal money) and CSV into data/
    Coverage is forced BEFORE deriving, so derived fields are computed once from the
    final drivers and can never go stale.
    Repeatability: one numpy Generator, seeded once, makes every random draw in a
    fixed order. Same seed + same as-of date + same config = identical tape.
    Columns are numpy arrays in a dict while building (fast, predictable types) and
    become a pandas DataFrame only at the end.
    Money is computed in float64, rounded to cents, and written as Decimal(14,2);
    a test checks the float amortization against an exact Decimal schedule.
"""

from __future__ import annotations

import argparse
import tomllib  # TECH: built into Python 3.11+; reads TOML config files
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.csv as pa_csv
import pyarrow.parquet as pq

from app.spec_stories import Story, equality_target, family, load_spec_stories, tier_column

# =============================================================================
# Paths, column list and types
# =============================================================================

# TECH: paths come from this file's location, not the current folder, so the
#   output always lands in <repo>/data/ wherever the command is run from.
BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
CONFIG_PATH = BACKEND_DIR / "app" / "config" / "loan_tape_gen.toml"
DEFAULT_OUT_DIR = REPO_ROOT / "data"

# TECH: the published tape schema, in output order, with its Arrow (Parquet) type.
#   docs/domain/loan-tape-schema.md documents every column; a test keeps them in sync.
MONEY = pa.decimal128(14, 2)  # BUSINESS: dollars and cents, exact, up to $999 billion
SCHEMA: dict[str, pa.DataType] = {
    # IDs
    "loan_id": pa.string(), "seller": pa.string(), "servicer": pa.string(),
    "channel": pa.string(),
    # Program and product
    "program": pa.string(), "product": pa.string(),
    # Dates and terms
    "orig_date": pa.date32(), "first_pay_date": pa.date32(), "maturity_date": pa.date32(),
    "orig_term": pa.int32(), "loan_age": pa.int32(), "remaining_term": pa.int32(),
    # Rate and balance
    "note_rate": pa.float64(), "orig_upb": MONEY, "current_upb": MONEY, "pi_payment": MONEY,
    # Borrower
    "fico": pa.int32(), "dti": pa.float64(), "first_time_buyer": pa.bool_(),
    # Collateral
    "property_type": pa.string(), "units": pa.int32(), "occupancy": pa.string(),
    "loan_purpose": pa.string(), "state": pa.string(),
    "appraised_value": MONEY, "current_value": MONEY,
    # LTV family
    "ltv": pa.float64(), "cltv": pa.float64(), "hcltv": pa.float64(), "mtm_ltv": pa.float64(),
    # Performance
    "dq_status": pa.string(), "days_past_due": pa.int32(), "pay_history_12m": pa.string(),
    "mod_flag": pa.bool_(), "forbearance_flag": pa.bool_(),
    # ARM details (null for fixed-rate loans)
    "arm_index": pa.string(), "margin": pa.float64(), "first_reset_date": pa.date32(),
    "initial_cap": pa.float64(), "periodic_cap": pa.float64(), "lifetime_cap": pa.float64(),
}
COLUMNS: list[str] = list(SCHEMA)

# BUSINESS: one character per month in pay_history_12m. Digits count missed
#   payments (0 = paid, 4 = 4 or more); letters are the MBA end states.
#   "-" means no payment was due yet (the loan had not reached its first payment).
HISTORY_CODE = {"Current": "0", "30": "1", "60": "2", "90": "3", "120+": "4",
                "FC": "F", "BK": "B", "REO": "R"}

# TECH: while building, the tape is a dict of equal-length numpy arrays.
Tape = dict[str, np.ndarray]
Config = dict[str, Any]


@dataclass(frozen=True)
class RunContext:
    """Everything one generation run shares.

    BUSINESS: the things that make a tape reproducible: the rulebook (config),
      the spec stories it must cover, the dice (seeded random generator) and the
      cut-off date.
    TECH: frozen dataclass so no step can swap the config or generator mid-run.
      as_of is a numpy datetime64 at day precision and must be the 1st of a month.
      stories are already validated by app.spec_stories.
    """

    cfg: Config
    rng: np.random.Generator
    as_of: np.datetime64
    stories: tuple[Story, ...]


# =============================================================================
# Small helpers: weighted picks, lookups, month arithmetic
# =============================================================================

def load_config(path: Path = CONFIG_PATH) -> Config:
    """Read the generator's TOML config.

    BUSINESS: the config is the single home of every illustrative threshold,
      distribution and minimum count; the code holds none of them.
    TECH: tomllib needs the file opened in binary mode. Returns nested dicts.
    """
    with path.open("rb") as f:
        return tomllib.load(f)


def pick(rng: np.random.Generator, weights: dict[str, float], size: int) -> np.ndarray:
    """Draw `size` labels at random in proportion to their weights.

    BUSINESS: how a mix like "50% Conventional, 15% FHA ..." becomes loans.
    TECH: weights need not sum to 1; they are normalized. Returns an object array
      of the dict's keys. Always draws `size` numbers, even if fewer are used, so the
      random stream (and therefore the tape) does not depend on the data.
    """
    keys = np.array(list(weights), dtype=object)
    p = np.array(list(weights.values()), dtype=float)
    return keys[rng.choice(len(keys), size=size, p=p / p.sum())]


def clipped_normal(rng: np.random.Generator, spec: dict[str, float], size: int) -> np.ndarray:
    """Bell-curve draws held inside a floor and a ceiling.

    BUSINESS: FICO and DTI cluster around a typical value with program limits on
      both sides (FHA FICO floor 580, conventional DTI cap 50).
    TECH: spec has mean, sd, min, max. Clipping piles a little mass at the limits,
      which real tapes also show (loans written right at the cap).
    """
    return np.clip(rng.normal(spec["mean"], spec["sd"], size), spec["min"], spec["max"])


def by_year(table: dict[str, float], years: np.ndarray) -> np.ndarray:
    """Look up a per-year value (loan limit, HPI change) for each loan's year.

    TECH: TOML keys are strings, so years are converted with str(). A missing year
      raises KeyError, which means the config needs a row for that year.
    """
    return np.array([table[str(int(y))] for y in years], dtype=float)


def by_month(table: dict[str, list[float]], dates: np.ndarray) -> np.ndarray:
    """Look up a per-month value (base mortgage rate) for each loan's date.

    BUSINESS: rates move within a year (2022 went from about 3% to over 6%), so
      a loan closed in October must not get January's rate.
    TECH: the table maps "YYYY" to 12 values, January first. Month index comes
      from datetime64[M] (months since 1970), modulo 12.
    """
    months = dates.astype("datetime64[M]").astype(int) % 12
    return np.array([table[str(int(y))][m] for y, m in zip(years_of(dates), months)], dtype=float)


def product_field(cfg: Config, products: np.ndarray, field: str, default: float = 0) -> np.ndarray:
    """Read one attribute (term, fixed_months, io_months) for each loan's product.

    TECH: returns floats; `default` fills products without that attribute
      (fixed-rate loans have no fixed_months, for example).
    """
    return np.array([cfg["products"][p].get(field, default) for p in products], dtype=float)


def years_of(dates: np.ndarray) -> np.ndarray:
    """Calendar year of each date. TECH: datetime64 counts years from 1970."""
    return dates.astype("datetime64[Y]").astype(int) + 1970


def year_start(years: np.ndarray | int) -> np.ndarray:
    """January 1 of each year, as datetime64[D]."""
    return (np.asarray(years) - 1970).astype("datetime64[Y]").astype("datetime64[D]")


def add_months(dates: np.ndarray, months: np.ndarray | int) -> np.ndarray:
    """First day of the month that is `months` after each date's month.

    BUSINESS: mortgage dates run on the 1st of the month (payment due dates,
      maturity, ARM change dates), so month arithmetic snaps to the 1st.
    TECH: datetime64[M] counts whole months. The offset is cast to timedelta64[M]
      explicitly, because numpy is deprecating bare integers in date arithmetic.
    """
    months_arr = np.asarray(months).astype(int).astype("timedelta64[M]")
    return (dates.astype("datetime64[M]") + months_arr).astype("datetime64[D]")


def add_days(dates: np.ndarray, days: np.ndarray | int) -> np.ndarray:
    """Each date plus a whole number of days (explicit timedelta64[D], see add_months)."""
    return dates + np.asarray(days).astype(int).astype("timedelta64[D]")


def round_to(values: np.ndarray, step: float) -> np.ndarray:
    """Round to the nearest multiple of `step` (dollars to $100, rates to 1/8)."""
    return np.round(values / step) * step


def choose(rng: np.random.Generator, candidates: np.ndarray, k: int, label: str) -> np.ndarray:
    """Pick k distinct loans at random from the candidate mask.

    BUSINESS: which loans get edited to meet a coverage minimum.
    TECH: returns row positions. Raises ValueError if too few candidates exist,
      which means the tape is too small or the config minimums are too high.
    """
    pool = np.flatnonzero(candidates)
    if pool.size < k:
        raise ValueError(f"Not enough loans to force {label}: need {k}, have {pool.size}.")
    return np.sort(rng.choice(pool, size=k, replace=False))


# =============================================================================
# Step 2: sample drivers
# =============================================================================

def make_loan_ids(rng: np.random.Generator, n: int) -> np.ndarray:
    """Unique loan IDs, "LN" plus 8 digits.

    BUSINESS: every loan needs a key the desk can quote back to the seller.
    TECH: draws distinct numbers from 10,000,000-99,999,999 without replacement,
      so IDs never collide and never start with 0.
    """
    numbers = rng.choice(90_000_000, size=n, replace=False) + 10_000_000
    return np.array([f"LN{x:08d}" for x in numbers], dtype=object)


def random_dates_in_years(ctx: RunContext, years: np.ndarray) -> np.ndarray:
    """A uniformly random day inside each given year, strictly before the as-of date.

    TECH: for the as-of year the window ends the day before as_of, so no loan is
      originated on or after the tape's cut-off.
    """
    start = year_start(years)
    end = np.minimum(year_start(years + 1), ctx.as_of)
    span_days = (end - start).astype(int)
    offset = np.floor(ctx.rng.random(len(years)) * span_days).astype(int)
    return add_days(start, offset)


def sample_orig_dates(ctx: RunContext, n: int) -> np.ndarray:
    """Origination dates following the vintage mix in the config.

    BUSINESS: real tapes are lumpy by vintage: 2020-2021 refi boom, fewer loans
      once rates rose in 2022. Vintage drives the note rate and loan limits.
    TECH: only years from first_year up to the as-of year are eligible.
    """
    vintage = ctx.cfg["vintage"]
    weights = {y: w for y, w in vintage["year_weights"].items()
               if int(y) >= vintage["first_year"] and year_start(int(y)) < ctx.as_of}
    years = pick(ctx.rng, weights, n).astype(int)
    return random_dates_in_years(ctx, years)


def is_arm(cfg: Config, products: np.ndarray) -> np.ndarray:
    """True for adjustable-rate products (those with a fixed_months period)."""
    return np.array(["fixed_months" in cfg["products"][p] for p in products], dtype=bool)


def sample_products(ctx: RunContext, programs: np.ndarray, years: np.ndarray) -> np.ndarray:
    """Product for each loan, from its program's product mix.

    BUSINESS: only real combinations: USDA is 30-year fixed only, IO is Non-QM
      only, and ARMs exist only from 2021 (when agency SOFR ARMs began).
    TECH: for each program, loans before the ARM start year draw from the mix with
      ARMs removed. Program order follows the config, keeping draws repeatable.
    """
    cfg, out = ctx.cfg, np.empty(len(programs), dtype=object)
    for name, spec in cfg["programs"].items():
        for arm_ok in (False, True):
            # TECH: split the program's loans into pre-2021 and 2021+ vintages.
            vintage_ok = (years >= cfg["arm"]["first_year"]) == arm_ok
            idx = np.flatnonzero((programs == name) & vintage_ok)
            mix = {p: w for p, w in spec["products"].items()
                   if arm_ok or "fixed_months" not in cfg["products"][p]}
            out[idx] = pick(ctx.rng, mix, idx.size)
    return out


def sample_ltv(rng: np.random.Generator, buckets: list[list[float]], size: int) -> np.ndarray:
    """LTV in percent from a bucketed distribution.

    BUSINESS: LTV is lumpy at program maximums (FHA 96.5, VA 100) and at 80, where
      mortgage insurance starts. Buckets reproduce those spikes.
    TECH: buckets are [low, high, weight]; pick a bucket, then uniform inside it.
      A bucket with low == high is a spike at exactly that LTV. Rounded to 0.01%.
    """
    b = np.array(buckets, dtype=float)
    which = rng.choice(len(b), size=size, p=b[:, 2] / b[:, 2].sum())
    return np.round(rng.uniform(b[which, 0], b[which, 1]), 2)


def sample_balance(ctx: RunContext, spec: dict[str, Any], years: np.ndarray) -> np.ndarray:
    """Original UPB in dollars, shaped by the program's balance rule.

    BUSINESS: loan limits define programs. Conforming loans stay at or under the
      FHFA baseline for their year; High-Balance sits between the baseline and the
      high-cost ceiling (150% of it); Jumbo is above $832,750 in every vintage.
    TECH: lognormal draws (right-skewed, like real balances) rounded to $100, then
      clipped to the program's floor and cap. Conforming medians scale with the
      year's limit, because balances grew as home prices rose.
    """
    rng, lim, size = ctx.rng, ctx.cfg["limits"], len(years)
    base = by_year(lim["baseline_by_year"], years)
    kind = spec["kind"]
    if kind == "high_balance":
        raw = base + (base * (lim["high_cost_multiple"] - 1)) * rng.random(size)
        return np.clip(round_to(raw, 100), base + 100, base * lim["high_cost_multiple"])
    median = spec["median"]
    if kind == "conforming":
        # BUSINESS: a 2015 loan is smaller than a 2026 loan; scale by the limit.
        median = median * base / max(lim["baseline_by_year"].values())
    raw = round_to(rng.lognormal(np.log(median), spec["sigma"], size), 100)
    if kind == "conforming":
        return np.clip(raw, spec["min"], base)
    if kind == "jumbo":
        return np.clip(raw, round_to(lim["jumbo_floor"], 100) + 100, spec["max"])
    return np.clip(raw, spec["min"], spec["max"])  # kind == "free" (Non-QM)


def sample_credit_and_balance(ctx: RunContext, programs: np.ndarray, years: np.ndarray) -> Tape:
    """FICO, DTI, LTV, balance, occupancy, purpose and first-time buyer, by program.

    BUSINESS: each program has its own borrower profile (FHA: lower FICO, higher
      LTV; Jumbo: high FICO, low LTV; Non-QM: more investors and cash-out).
    TECH: loops programs in config order and fills each program's rows. FICO is an
      integer; DTI is percent with one decimal.
    """
    rng, n = ctx.rng, len(programs)
    t: Tape = {"fico": np.zeros(n), "dti": np.zeros(n), "ltv": np.zeros(n),
               "orig_upb": np.zeros(n), "occupancy": np.empty(n, dtype=object),
               "loan_purpose": np.empty(n, dtype=object),
               "first_time_buyer": np.zeros(n, dtype=bool)}
    for name, spec in ctx.cfg["programs"].items():
        idx = np.flatnonzero(programs == name)
        t["fico"][idx] = np.round(clipped_normal(rng, spec["fico"], idx.size))
        t["dti"][idx] = np.round(clipped_normal(rng, spec["dti"], idx.size), 1)
        t["ltv"][idx] = sample_ltv(rng, spec["ltv_buckets"], idx.size)
        t["orig_upb"][idx] = sample_balance(ctx, spec["balance"], years[idx])
        t["occupancy"][idx] = pick(rng, spec["occupancy"], idx.size)
        t["loan_purpose"][idx] = pick(rng, spec["purpose"], idx.size)
        t["first_time_buyer"][idx] = rng.random(idx.size) < spec["first_time_buyer_rate"]
    # BUSINESS: only someone buying a home to live in can be a first-time buyer.
    t["first_time_buyer"] &= (t["loan_purpose"] == "Purchase") & (t["occupancy"] == "Primary")
    t["fico"] = t["fico"].astype(int)
    return t


def apply_ltv_caps(cfg: Config, t: Tape) -> None:
    """Hold LTV under program maximums for cash-out, investor and second homes.

    BUSINESS: agencies allow less leverage on riskier purposes, e.g. conventional
      cash-out refis max out at 80% LTV, FHA cash-out at 80%, investor at 85%.
    TECH: each max_ltv key is matched against both purpose and occupancy. Edits t
      in place.
    """
    for name, spec in cfg["programs"].items():
        for key, cap in spec["max_ltv"].items():
            hit = (t["program"] == name) & ((t["loan_purpose"] == key) | (t["occupancy"] == key))
            t["ltv"][hit] = np.minimum(t["ltv"][hit], cap)


def sample_collateral(ctx: RunContext, n: int) -> Tape:
    """Property type, units and state.

    BUSINESS: property type and state drive pricing and spec-pool stories
      (New York and Puerto Rico pools trade above TBA).
    TECH: units are 1 except for 2-4 Unit properties, which draw 2, 3 or 4.
    """
    coll, rng = ctx.cfg["collateral"], ctx.rng
    prop = pick(rng, coll["property_type"], n)
    multi = pick(rng, coll["multi_units"], n).astype(int)
    return {"property_type": prop,
            "units": np.where(prop == "2-4 Unit", multi, 1),
            "state": pick(rng, coll["states"], n)}


def sample_parties(ctx: RunContext, n: int) -> Tape:
    """Channel, seller and servicer.

    BUSINESS: the seller delivers the loan; the servicer collects payments. Some
      sellers keep servicing ("servicing retained"); the rest sell it.
    TECH: servicer equals seller when retained, otherwise a fictional servicer.
    """
    p, rng = ctx.cfg["parties"], ctx.rng
    seller = np.array(p["sellers"], dtype=object)[rng.integers(0, len(p["sellers"]), n)]
    other = np.array(p["servicers"], dtype=object)[rng.integers(0, len(p["servicers"]), n)]
    retained = rng.random(n) < p["servicing_retained_rate"]
    return {"channel": pick(rng, p["channel"], n), "seller": seller,
            "servicer": np.where(retained, seller, other)}


def sample_sub_liens(ctx: RunContext, programs: np.ndarray) -> Tape:
    """Subordinate liens behind the first mortgage, as percent of value.

    BUSINESS: a closed-end second is fully drawn; a HELOC is a credit line that
      may be partly drawn. CLTV counts what is drawn; HCLTV counts the full line.
    TECH: returns two internal columns (dropped before output): _sub_drawn_pct and
      _sub_line_pct, in LTV points. Excluded programs get no subordinate lien.
    """
    s, rng, n = ctx.cfg["sub_liens"], ctx.rng, len(programs)
    u = rng.random(n)
    closed = u < s["closed_end_rate"]
    heloc = ~closed & (u < s["closed_end_rate"] + s["heloc_rate"])
    closed_pct = rng.uniform(*s["closed_end_pct"], n)
    line_pct = rng.uniform(*s["heloc_line_pct"], n)
    drawn_share = rng.random(n)
    allowed = ~np.isin(programs, s["excluded_programs"])
    drawn = np.where(closed, closed_pct, np.where(heloc, line_pct * drawn_share, 0.0))
    line = np.where(closed, closed_pct, np.where(heloc, line_pct, 0.0))
    return {"_sub_drawn_pct": np.round(drawn * allowed, 2),
            "_sub_line_pct": np.round(line * allowed, 2)}


def sample_drivers(ctx: RunContext, n: int) -> Tape:
    """Step 2: draw every loan's independent attributes.

    BUSINESS: these are the facts a loan officer records at origination. Every
      other field (rate, payment, balance today, LTV family) follows from them.
    TECH: order matters for repeatability: each call consumes random numbers in a
      fixed sequence. Program first, then year, because products and balances
      depend on both.
    """
    cfg, rng = ctx.cfg, ctx.rng
    t: Tape = {"loan_id": make_loan_ids(rng, n),
               "program": pick(rng, {k: v["weight"] for k, v in cfg["programs"].items()}, n)}
    t["orig_date"] = sample_orig_dates(ctx, n)
    years = years_of(t["orig_date"])
    t["product"] = sample_products(ctx, t["program"], years)
    t.update(sample_credit_and_balance(ctx, t["program"], years))
    apply_ltv_caps(cfg, t)
    t.update(sample_collateral(ctx, n))
    t.update(sample_parties(ctx, n))
    t.update(sample_sub_liens(ctx, t["program"]))
    return t


# =============================================================================
# Step 3: force coverage
# =============================================================================
# BUSINESS: random sampling can leave a demo with no Puerto Rico loans or no REO.
#   These steps top up each minimum by editing the drivers of a few loans.
# TECH: `locked` marks loans already edited, so a later step cannot undo an earlier
#   one. Candidates exclude loans that already qualify, so topping up one tier
#   never drains another. All picks use the same seeded generator.

def force_high_ltv(ctx: RunContext, t: Tape, locked: np.ndarray) -> None:
    """Guarantee loans with original LTV above 125.

    BUSINESS: only FHFA's high-LTV refinance programs (HARP, to 2018) let
      underwater borrowers refinance above 125% LTV, so forced loans become
      conventional rate/term refis from 2015-2018 with no second lien.
    TECH: candidates are unlocked conventional fixed-rate loans.
    """
    spec = ctx.cfg["coverage"]["high_ltv"]
    need = spec["count"] - int((t["ltv"] > 125).sum())
    if need <= 0:
        return
    fixed = ~is_arm(ctx.cfg, t["product"]) & (product_field(ctx.cfg, t["product"], "io_months") == 0)
    cand = ~locked & (t["program"] == spec["program"]) & fixed
    idx = choose(ctx.rng, cand, need, "LTV > 125")
    years = ctx.rng.integers(spec["years"][0], spec["years"][1] + 1, need)
    t["orig_date"][idx] = random_dates_in_years(ctx, years)
    t["ltv"][idx] = np.round(ctx.rng.uniform(*spec["ltv"], need), 2)
    t["loan_purpose"][idx] = spec["purpose"]
    t["first_time_buyer"][idx] = False
    t["_sub_drawn_pct"][idx] = 0.0
    t["_sub_line_pct"][idx] = 0.0
    locked[idx] = True


def story_mask(t: Tape, story: Story) -> np.ndarray:
    """Which loans already have a spec story, for the rule shapes the generator forces.

    BUSINESS: a loan has the story when its product is listed and its rule holds.
    TECH: the generator works on numpy arrays, not SQL, so it evaluates only the
      two shapes it knows how to force: `orig_upb <= <cap>` and `state = '<code>'`.
      Any other shape with a coverage minimum raises ValueError, because the
      generator would not know which field to change. (Tests check the real SQL
      in DuckDB against the written tape.)
    """
    products = np.isin(t["product"], story.products)
    if tier_column(story) == "orig_upb" and story.cap is not None:
        return products & (t["orig_upb"] <= story.cap)
    target = equality_target(story)
    if target is not None and target[0] == "state":
        return products & (t["state"] == target[1])
    raise ValueError(f"Cannot force story {story.name}: the generator can only force "
                     "`orig_upb <= {cap}` tiers and `state = '..'` rules.")


def force_tiered_story(ctx: RunContext, t: Tape, locked: np.ndarray, name: str, count: int) -> None:
    """Guarantee `count` loans in every band of a tiered balance story (LLB).

    BUSINESS: LLB pools are sorted by maximum original balance; the tiers come
      from spec_stories.toml. Small loans prepay slowly, so each tier earns a
      pay-up over TBA and the desk needs loans in every band.
    TECH: bands are (previous cap, cap] among loans with an eligible product.
      Candidates are unlocked loans above the top cap with an eligible product and
      program, so moving one never empties another band. New balances are uniform
      inside the band (never below the config floor), rounded to $100.
    """
    tiers, spec = family(ctx.stories, name), ctx.cfg["coverage"]["tiered"][name]
    caps = np.array([s.cap for s in tiers], dtype=float)
    for story, low, cap in zip(tiers, np.concatenate([[0.0], caps[:-1]]), caps):
        eligible = story_mask(t, story) & (t["orig_upb"] > low)
        need = count - int(eligible.sum())
        if need <= 0:
            continue
        cand = (~locked & np.isin(t["product"], story.products)
                & np.isin(t["program"], spec["programs"]) & (t["orig_upb"] > caps[-1]))
        idx = choose(ctx.rng, cand, need, story.name)
        new_low = max(low, spec["floor"] - 100) + 100
        t["orig_upb"][idx] = np.clip(round_to(ctx.rng.uniform(new_low, cap, need), 100), new_low, cap)
        locked[idx] = True


def force_state_story(ctx: RunContext, t: Tape, locked: np.ndarray, story: Story, count: int,
                      protected: list[str]) -> None:
    """Guarantee `count` loans in a state story (NY, PR).

    BUSINESS: New York and Puerto Rico loans are less likely to pay off early, so
      both form spec pools (sources in docs/public-sources.md).
    TECH: candidates are unlocked loans with an eligible product, outside every
      state that has its own minimum (`protected`), so filling PR never drains NY.
    """
    need = count - int(story_mask(t, story).sum())
    if need <= 0:
        return
    _, state = equality_target(story) or ("", "")
    cand = ~locked & np.isin(t["product"], story.products) & ~np.isin(t["state"], protected)
    idx = choose(ctx.rng, cand, need, story.name)
    t["state"][idx] = state
    locked[idx] = True


def force_stories(ctx: RunContext, t: Tape, locked: np.ndarray) -> None:
    """Meet every [coverage.stories] minimum, then lock every loan that counts.

    BUSINESS: the stories (which loans qualify) come from spec_stories.toml; only
      the minimum counts come from loan_tape_gen.toml.
    TECH: tiered stories fill each band; untiered ones must be state rules.
      Afterwards, every loan that counts toward a minimum is locked, so the later
      ARM step cannot turn it into an ARM and drop it out of its story.
    """
    minimums = ctx.cfg["coverage"]["stories"]
    groups = {name: family(ctx.stories, name) for name in minimums}
    protected = [target[1] for g in groups.values() if g[0].cap is None
                 and (target := equality_target(g[0])) is not None]
    for name, count in minimums.items():
        if groups[name][0].cap is not None:
            force_tiered_story(ctx, t, locked, name, count)
        else:
            force_state_story(ctx, t, locked, groups[name][0], count, protected)
    for group in groups.values():
        for story in group:
            locked |= story_mask(t, story)


def first_reset_dates(cfg: Config, products: np.ndarray, orig_dates: np.ndarray) -> np.ndarray:
    """First rate change date for each ARM; NaT for fixed-rate loans.

    BUSINESS: a 5/6 ARM keeps its starting rate for 60 payments; the rate changes
      on the 1st of the month before payment 61 (interest is paid in arrears).
    TECH: first payment is 2 months after the origination month, so
      reset = first payment + (fixed_months - 1) months.
    """
    fixed_months = product_field(cfg, products, "fixed_months", default=np.nan)
    first_pay = add_months(orig_dates, 2)
    out = np.full(len(products), np.datetime64("NaT", "D"), dtype="datetime64[D]")
    arm = ~np.isnan(fixed_months)
    out[arm] = add_months(first_pay[arm], fixed_months[arm] - 1)
    return out


def force_arm_resets(ctx: RunContext, t: Tape, locked: np.ndarray) -> None:
    """Guarantee ARMs whose first reset falls in the next few months.

    BUSINESS: an ARM about to reset may see a payment shock and often prepays,
      which matters for pricing and for which pools it can go in.
    TECH: forced loans become the configured ARM product; the origination date is
      worked backwards from a target reset month inside [as_of, as_of + window).
    """
    cfg, spec = ctx.cfg, ctx.cfg["coverage"]["arm_reset"]
    window_end = add_months(np.array([ctx.as_of]), spec["window_months"])[0]
    reset = first_reset_dates(cfg, t["product"], t["orig_date"])
    hit = (reset >= ctx.as_of) & (reset < window_end)
    need = spec["count"] - int(hit.sum())
    if need <= 0:
        return
    cand = ~locked & ~hit & np.isin(t["program"], spec["programs"])
    idx = choose(ctx.rng, cand, need, "ARM resets")
    # TECH: reset month -> first payment month -> origination month, then a day 1-28.
    target = add_months(np.full(need, ctx.as_of), ctx.rng.integers(0, spec["window_months"], need))
    first_pay = add_months(target, -(cfg["products"][spec["product"]]["fixed_months"] - 1))
    orig = add_days(add_months(first_pay, -2), ctx.rng.integers(0, 28, need))
    if years_of(orig).min() < cfg["arm"]["first_year"]:
        raise ValueError("as-of date too early: forced ARMs would predate SOFR ARMs.")
    t["product"][idx] = spec["product"]
    t["orig_date"][idx] = orig
    locked[idx] = True


def apply_balance_limits(ctx: RunContext, t: Tape) -> None:
    """Re-apply loan limits after coverage edits changed some origination years.

    BUSINESS: moving a conventional loan from 2024 back to 2016 lowers its limit
      from $766,550 to $417,000, so its balance must follow.
    TECH: only rows outside their year's limits change. Edits t in place.
    """
    lim = ctx.cfg["limits"]
    base = by_year(lim["baseline_by_year"], years_of(t["orig_date"]))
    for name, spec in ctx.cfg["programs"].items():
        rows = t["program"] == name
        kind = spec["balance"]["kind"]
        if kind == "conforming":
            t["orig_upb"][rows] = np.minimum(t["orig_upb"][rows], base[rows])
        elif kind == "high_balance":
            t["orig_upb"][rows] = np.clip(t["orig_upb"][rows], base[rows] + 100,
                                          base[rows] * lim["high_cost_multiple"])


def force_coverage(ctx: RunContext, t: Tape) -> None:
    """Step 3: meet every coverage minimum, then restore loan limits.

    TECH: order is high LTV, spec stories (LLB tiers, NY, PR), ARM resets. Each
      step locks what it edits. Delinquency minimums are met later, in step 5,
      because they change only performance fields.
    """
    locked = np.zeros(len(t["loan_id"]), dtype=bool)
    for step in (force_high_ltv, force_stories, force_arm_resets):
        step(ctx, t, locked)
    apply_balance_limits(ctx, t)


# =============================================================================
# Step 4: derive terms, rates, values and ARM fields
# =============================================================================

def derive_terms(ctx: RunContext, t: Tape) -> None:
    """Payment dates, term, loan age and remaining term.

    BUSINESS: a loan closed in January makes its first payment on March 1 (one
      month skipped, because interest is paid in arrears). Loan age is the number of
      payments that have come due before the as-of date; remaining term is what is
      left on the original schedule.
    TECH: maturity = first payment + (term - 1) months. loan_age is clipped to
      [0, term]; a loan whose first payment is on or after as_of has age 0.
    """
    t["orig_term"] = product_field(ctx.cfg, t["product"], "term").astype(int)
    t["first_pay_date"] = add_months(t["orig_date"], 2)
    t["maturity_date"] = add_months(t["first_pay_date"], t["orig_term"] - 1)
    months = (ctx.as_of.astype("datetime64[M]") - t["first_pay_date"].astype("datetime64[M]"))
    t["loan_age"] = np.clip(months.astype(int), 0, t["orig_term"])
    t["remaining_term"] = t["orig_term"] - t["loan_age"]


def band_lookup(values: np.ndarray, bands: list[list[float]]) -> np.ndarray:
    """Add-on from a banded grid such as [[740, 0.0], [680, 0.125], [0, 0.75]].

    TECH: bands are listed from the highest floor down; the first floor the value
      meets wins (np.select checks conditions in order).
    """
    return np.select([values >= floor for floor, _ in bands], [adj for _, adj in bands],
                     default=bands[-1][1])


def derive_note_rate(ctx: RunContext, t: Tape) -> None:
    """Note rate in percent: market rate for the vintage plus credit add-ons.

    BUSINESS: note_rate = base 30-year rate for the origination MONTH
                          (FHFA NMDB; MBA for 2026; see the config)
                        + product spread (15-year and ARMs are cheaper)
                        + program add-on (Non-QM about 1.5 points higher)
                        + FICO, LTV, occupancy and purpose add-ons (LLPA-style)
                        + loan-level noise,
      rounded to the nearest 1/8 (0.125%), because lenders quote in eighths.
    TECH: noise is normal with sd from config. Floored at min_rate. 3 decimals.
    """
    r = ctx.cfg["rates"]
    rate = (by_month(r["base_rate_30y_by_month"], t["orig_date"])
            + np.array([r["product_spread"][p] for p in t["product"]])
            + np.array([ctx.cfg["programs"][p]["rate_adj"] for p in t["program"]])
            + band_lookup(t["fico"], r["fico_adj"])
            + band_lookup(t["ltv"], r["ltv_adj"])
            + np.array([r["occupancy_adj"][o] for o in t["occupancy"]])
            + np.array([r["purpose_adj"][p] for p in t["loan_purpose"]])
            + ctx.rng.normal(0, r["noise_sd"], len(t["fico"])))
    t["note_rate"] = np.round(np.maximum(round_to(rate, r["increment"]), r["min_rate"]), 3)


def hpi_level(cfg: Config, dates: np.ndarray) -> np.ndarray:
    """House price index level on each date (Jan 1 of the first year = 1.0).

    BUSINESS: home values rise and fall with the market; the index measures how
      much a typical home's value changed between two dates.
    TECH: level at Jan 1 of year y = product of (1 + annual change) for earlier
      years; within a year it compounds by the fraction of the year elapsed.
    """
    table = cfg["hpi"]["annual_change_pct_by_year"]
    first = min(int(y) for y in table)
    growth = np.array([1 + table[str(first + i)] / 100 for i in range(len(table))])
    jan1_level = np.concatenate([[1.0], np.cumprod(growth)])
    years = years_of(dates)
    if years.min() < first or years.max() >= first + len(table):
        raise ValueError("HPI table in config does not cover every date.")
    i = years - first
    frac = (dates - year_start(years)).astype(int) / 365.25
    return jan1_level[i] * growth[i] ** frac


def derive_values(ctx: RunContext, t: Tape) -> None:
    """Appraised value, current value, LTV, CLTV and HCLTV.

    BUSINESS: LTV (%)   = original UPB / appraised value x 100
              CLTV (%)  = LTV + drawn subordinate liens (% of value)
              HCLTV (%) = LTV + full HELOC line (% of value)
      Current value = appraised value x HPI change since origination x a
      home-specific factor, so some homes beat the market and some lag it.
    TECH: appraised value is rounded UP to $100 so the recomputed LTV never exceeds
      the sampled one (VA stays at or under 100). Current value rounds to $100.
    """
    appraised = np.ceil(t["orig_upb"] / (t["ltv"] / 100) / 100) * 100
    t["appraised_value"] = appraised
    t["ltv"] = np.round(t["orig_upb"] / appraised * 100, 2)
    t["cltv"] = np.round(t["ltv"] + t["_sub_drawn_pct"], 2)
    t["hcltv"] = np.round(t["ltv"] + t["_sub_line_pct"], 2)
    hpi_change = hpi_level(ctx.cfg, np.full(len(appraised), ctx.as_of)) / hpi_level(ctx.cfg, t["orig_date"])
    noise = ctx.rng.lognormal(0, ctx.cfg["hpi"]["loan_noise_sd"], len(appraised))
    t["current_value"] = round_to(appraised * hpi_change * noise, 100)


def derive_arm_fields(ctx: RunContext, t: Tape) -> None:
    """Index, margin, first reset date and caps for ARMs; null for fixed loans.

    BUSINESS: after the fixed period an ARM's rate becomes index + margin, limited
      by caps: initial cap (first change), periodic cap (each later change) and
      lifetime cap (over the start rate), all in percentage points. Example 5/6
      ARM at 6.000% with 2/1/5 caps: first reset at most 8.000%, never above 11.000%.
    TECH: caps come from the product, margin from the program. Missing values are
      None / NaN / NaT, which become nulls in Parquet and blanks in CSV.
    """
    cfg, n = ctx.cfg, len(t["product"])
    arm = is_arm(cfg, t["product"])
    t["arm_index"] = np.where(arm, cfg["arm"]["index"], None).astype(object)
    t["margin"] = np.where(arm, [cfg["arm"]["margin_by_program"].get(p, np.nan)
                                 for p in t["program"]], np.nan)
    t["first_reset_date"] = first_reset_dates(cfg, t["product"], t["orig_date"])
    caps = np.full((n, 3), np.nan)
    for i in np.flatnonzero(arm):
        caps[i] = cfg["products"][t["product"][i]]["caps"]
    t["initial_cap"], t["periodic_cap"], t["lifetime_cap"] = caps[:, 0], caps[:, 1], caps[:, 2]


def derive(ctx: RunContext, t: Tape) -> None:
    """Step 4: compute every field that follows from the drivers."""
    derive_terms(ctx, t)
    derive_note_rate(ctx, t)
    derive_values(ctx, t)
    derive_arm_fields(ctx, t)


# =============================================================================
# Amortization (used in step 5, once missed payments are known)
# =============================================================================

def level_payment(principal: np.ndarray, rate_pct: np.ndarray, n_months: np.ndarray) -> np.ndarray:
    """Monthly principal and interest (P&I) payment of a fully amortizing loan.

    BUSINESS: the standard mortgage payment formula:
        P = L x r / (1 - (1 + r)^-n)
      L = loan amount ($), r = note rate / 12 as a decimal (6% -> 0.005 per month),
      n = number of monthly payments. Example: $200,000 at 6% for 360 months is
      $1,199.10 a month.
    TECH: vectorized; rate must be above zero (the config floors it at min_rate).
    """
    r = rate_pct / 1200
    return principal * r / (1 - (1 + r) ** (-n_months))


def balance_after(principal: np.ndarray, rate_pct: np.ndarray, payment: np.ndarray,
                  k: np.ndarray) -> np.ndarray:
    """Scheduled balance after k payments, in closed form.

    BUSINESS: B_k = L x (1 + r)^k - P x ((1 + r)^k - 1) / r
      The loan grows by monthly interest and shrinks by each payment; this is the
      sum of that month-by-month schedule without looping.
    TECH: float64; callers round to cents. A test compares it to an exact Decimal
      month-by-month schedule.
    """
    r = rate_pct / 1200
    growth = (1 + r) ** k
    return principal * growth - payment * (growth - 1) / r


def derive_balances(ctx: RunContext, t: Tape, paid: np.ndarray) -> None:
    """P&I payment and current UPB from the amortization schedule.

    BUSINESS: current UPB is the scheduled balance after the payments actually made
      (loan age minus missed payments), so a delinquent loan shows the balance as
      of its last paid installment. Interest-only loans pay interest only
      (P = L x r) for io_months, then amortize over the remaining months.
      pi_payment is the payment due next on the schedule.
    TECH: payments are rounded to cents first, then balances use that rounded
      payment, like a servicer's schedule. Balances are clipped to [0, orig_upb].
      ARMs use their start rate throughout (no reset recast; see the schema doc).
    """
    upb, rate = t["orig_upb"], t["note_rate"]
    io = product_field(ctx.cfg, t["product"], "io_months")
    amort_pay = np.round(level_payment(upb, rate, t["orig_term"] - io), 2)
    io_pay = np.round(upb * rate / 1200, 2)
    amort_k = np.maximum(paid - io, 0)
    balance = np.where(amort_k > 0, balance_after(upb, rate, amort_pay, amort_k), upb)
    t["current_upb"] = np.clip(np.round(balance, 2), 0, upb)
    t["pi_payment"] = np.where((io > 0) & (t["loan_age"] < io), io_pay, amort_pay)


# =============================================================================
# Step 5: delinquency, pay history, flags, current balance
# =============================================================================

def risk_logit(cfg: Config, t: Tape) -> np.ndarray:
    """Credit risk score in log-odds, before the intercept.

    BUSINESS: lower FICO, higher DTI, higher LTV, investor properties and cash-out
      refis all make a borrower more likely to fall behind:
        score = b_fico x (FICO - 700)/100 + b_dti x (DTI - 36)/10
              + b_ltv x (LTV - 80)/10 + b_inv x investor + b_co x cash-out
    TECH: each driver is centered so a "typical" loan scores about 0. Coefficients
      are illustrative and live in config.
    """
    d = cfg["delinquency"]
    return (d["fico_per_100"] * (t["fico"] - 700) / 100
            + d["dti_per_10"] * (t["dti"] - 36) / 10
            + d["ltv_per_10"] * (t["ltv"] - 80) / 10
            + d["investor"] * (t["occupancy"] == "Investor")
            + d["cash_out"] * (t["loan_purpose"] == "Cash-Out Refi"))


def sigmoid(z: np.ndarray | float) -> np.ndarray:
    """Logistic function: turns log-odds into a probability between 0 and 1."""
    return 1 / (1 + np.exp(-z))


def solve_intercept(score: np.ndarray, target: float) -> float:
    """Intercept that makes the average delinquency probability hit the target.

    BUSINESS: lets the desk say "about 7% delinquent" while keeping each loan's
      relative risk from its score.
    TECH: the mean of sigmoid(c + score) rises with c, so bisection on [-30, 30]
      converges; 100 halvings is far below float precision.
    """
    lo, hi = -30.0, 30.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if sigmoid(mid + score).mean() < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def fallback_status(age: np.ndarray) -> np.ndarray:
    """Most severe bucket a young loan can be in: 1 payment due -> 30 at most.

    BUSINESS: a loan with two payments due cannot be 90 days late.
    """
    return np.select([age == 1, age == 2, age == 3], ["30", "60", "90"], default="120+").astype(object)


def draw_missed(ctx: RunContext, status: np.ndarray, age: np.ndarray) -> np.ndarray:
    """Missed payment count for each loan, consistent with its status and age.

    BUSINESS: 30 = 1 missed, 60 = 2, 90 = 3, 120+ = 4 or more; FC and REO come
      after a long delinquency; BK can still be paying (0 missed).
    TECH: draws uniformly in [min, min(max, loan_age)] from config. Current = 0.
    """
    ranges = ctx.cfg["delinquency"]["missed_payments"]
    lo = np.array([ranges[s][0] if s in ranges else 0 for s in status])
    hi = np.array([ranges[s][1] if s in ranges else 0 for s in status])
    hi = np.minimum(hi, age)
    return (lo + np.floor(ctx.rng.random(len(status)) * (hi - lo + 1))).astype(int)


def assign_delinquency(ctx: RunContext, t: Tape, score: np.ndarray) -> np.ndarray:
    """Draw each loan's MBA status from its risk score.

    BUSINESS: riskier loans are more often delinquent, and delinquent loans split
      across buckets in proportions like an MBA survey (more 30s than REOs).
    TECH: only loans with at least one payment due can be delinquent, so the
      target is scaled up for that subset. Buckets a loan is too young for are
      replaced by the most severe one it can reach.
    """
    d, n, age = ctx.cfg["delinquency"], len(score), t["loan_age"]
    eligible = age >= 1
    target = min(d["target_rate"] * n / max(int(eligible.sum()), 1), 0.99)
    c = solve_intercept(score[eligible], target)
    is_dq = eligible & (ctx.rng.random(n) < sigmoid(c + score))
    status = np.where(is_dq, pick(ctx.rng, d["bucket_weights"], n), "Current").astype(object)
    min_missed = np.array([d["missed_payments"].get(s, [0])[0] for s in status])
    too_young = is_dq & (age < min_missed)
    status[too_young] = fallback_status(age[too_young])
    return status


def force_delinquency(ctx: RunContext, t: Tape, status: np.ndarray, score: np.ndarray) -> None:
    """Meet the minimum counts of 90+, FC and REO loans.

    BUSINESS: the riskiest current loans that are old enough are the ones moved,
      so forced delinquency still follows credit quality.
    TECH: deterministic (sorted by score, highest first). Edits status in place.
    """
    ranges = ctx.cfg["delinquency"]["missed_payments"]
    for rule in ctx.cfg["coverage"]["delinquency"]:
        need = rule["count"] - int(np.isin(status, rule["statuses"]).sum())
        if need <= 0:
            continue
        cand = np.flatnonzero((status == "Current") &
                              (t["loan_age"] >= max(ranges[rule["assign"]][0], 1)))
        if cand.size < need:
            raise ValueError(f"Not enough seasoned loans to force {rule['label']}.")
        idx = cand[np.argsort(-score[cand], kind="stable")[:need]]
        status[idx] = rule["assign"]


def days_past_due(ctx: RunContext, t: Tape, missed: np.ndarray) -> np.ndarray:
    """Calendar days from the oldest unpaid due date to the as-of date.

    BUSINESS: with as_of on Nov 1, one missed payment (due Oct 1) is 31 days past
      due, two (due Sep 1) are 61 days: the MBA 30 and 60 buckets.
    TECH: oldest unpaid due date = first payment + (age - missed) months. 0 when
      nothing is missed.
    """
    oldest_unpaid = add_months(t["first_pay_date"], t["loan_age"] - missed)
    return np.where(missed > 0, (ctx.as_of - oldest_unpaid).astype(int), 0)


def history_string(status: str, missed: int, age: int, d: Config) -> str:
    """Twelve-month pay history for one loan, oldest month first.

    BUSINESS: reading right to left, the loan rolls back one bucket per month (a
      loan cannot jump from current to 60 days late). FC loans show 120+ before
      foreclosure; REO loans show FC before REO. Months before the first payment
      show "-".
    TECH: j counts months back from the latest (j = 0 is the as-of month). REO and
      FC segments are sized so the digit right before them is 4 (120+).
    """
    reo = int(np.clip(missed - 6, 1, d["max_reo_months"])) if status == "REO" else 0
    fc = max(1, missed - reo - 4) if status in ("FC", "REO") else 0
    bk = int(np.clip(missed, 1, d["max_bk_months"])) if status == "BK" else 0
    chars = []
    for j in range(12):
        if j >= age:
            chars.append("-")
        elif j < reo:
            chars.append("R")
        elif j < reo + fc:
            chars.append("F")
        elif j < bk:
            chars.append("B")
        else:
            chars.append(str(min(max(missed - j, 0), 4)))
    return "".join(reversed(chars))


def apply_delinquency(ctx: RunContext, t: Tape) -> None:
    """Step 5: status, missed payments, days past due, pay history, flags, balances.

    BUSINESS: performance fields come from credit risk; balances come last because
      a delinquent loan's balance stops at its last paid installment.
    TECH: mtm_ltv (%) = current UPB / current value x 100 is computed after the
      balance. Mod and forbearance flags are more likely on delinquent loans.
    """
    d, n = ctx.cfg["delinquency"], len(t["loan_id"])
    score = risk_logit(ctx.cfg, t)
    status = assign_delinquency(ctx, t, score)
    force_delinquency(ctx, t, status, score)
    missed = draw_missed(ctx, status, t["loan_age"])
    t["dq_status"] = status
    t["days_past_due"] = days_past_due(ctx, t, missed)
    t["pay_history_12m"] = np.array([history_string(s, m, a, d) for s, m, a
                                     in zip(status, missed, t["loan_age"])], dtype=object)
    current = status == "Current"
    t["mod_flag"] = ctx.rng.random(n) < np.where(current, d["mod_rate"]["current"],
                                                 d["mod_rate"]["delinquent"])
    t["forbearance_flag"] = ctx.rng.random(n) < np.where(current, d["forbearance_rate"]["current"],
                                                         d["forbearance_rate"]["delinquent"])
    derive_balances(ctx, t, t["loan_age"] - missed)
    t["mtm_ltv"] = np.round(t["current_upb"] / t["current_value"] * 100, 2)


# =============================================================================
# Step 6: assemble and write
# =============================================================================

def validate_inputs(cfg: Config, n: int, as_of: np.datetime64) -> None:
    """Reject runs the generator cannot do correctly.

    BUSINESS: the tape is cut at a month boundary, and must be big enough to hold
      every coverage minimum.
    TECH: raises ValueError with a plain-English message.
    """
    if n < cfg["run"]["min_n"]:
        raise ValueError(f"--n must be at least {cfg['run']['min_n']} to meet coverage minimums.")
    if as_of != as_of.astype("datetime64[M]").astype("datetime64[D]"):
        raise ValueError("--as-of must be the 1st of a month, e.g. 2026-11-01.")
    year = str(int(years_of(np.array([as_of]))[0]))
    rates = cfg["rates"]["base_rate_30y_by_month"]
    for table in (rates, cfg["limits"]["baseline_by_year"], cfg["hpi"]["annual_change_pct_by_year"]):
        if year not in table:
            raise ValueError(f"Config has no {year} row for rates, limits or HPI.")
    if any(len(months) != 12 for months in rates.values()):
        raise ValueError("Every base_rate_30y_by_month row needs 12 monthly values.")


def generate_tape(n: int | None = None, seed: int | None = None, as_of: str | None = None,
                  cfg: Config | None = None, stories: Sequence[Story] | None = None) -> pd.DataFrame:
    """Build a synthetic loan tape in memory.

    BUSINESS: one row per loan, every field the desk needs, reproducible from the
      seed so every demo shows the same tape.
    TECH: arguments default to the config's run section and to the validated
      stories in spec_stories.toml (tests pass edited copies of either). Runs
      steps 2-5 on a dict of numpy arrays, then returns a DataFrame with COLUMNS in
      order. Raises ValueError for invalid inputs or unsafe story rules.
    """
    cfg = cfg or load_config()
    if stories is None:
        stories = load_spec_stories(COLUMNS, products=list(cfg["products"]))
    run = cfg["run"]
    n = run["n_default"] if n is None else n
    seed = run["seed_default"] if seed is None else seed
    as_of_day = np.datetime64(as_of or run["as_of_default"], "D")
    validate_inputs(cfg, n, as_of_day)
    ctx = RunContext(cfg=cfg, rng=np.random.default_rng(seed), as_of=as_of_day,
                     stories=tuple(stories))
    t = sample_drivers(ctx, n)
    force_coverage(ctx, t)
    derive(ctx, t)
    apply_delinquency(ctx, t)
    return pd.DataFrame({col: t[col] for col in COLUMNS})


def to_arrow(df: pd.DataFrame) -> pa.Table:
    """Convert the tape to an Arrow table with the published column types.

    BUSINESS: money is stored as exact Decimal dollars and cents, so totals in
      DuckDB match a calculator to the penny.
    TECH: money goes through Python Decimal from a 2-decimal string (no float
      artifacts). Dates go through numpy datetime64[D] -> date32. Missing values
      (NaN, None, NaT) become nulls.
    """
    arrays = []
    for col, typ in SCHEMA.items():
        if typ == MONEY:
            arrays.append(pa.array([None if pd.isna(v) else Decimal(f"{v:.2f}") for v in df[col]],
                                   type=typ))
        elif typ == pa.date32():
            arrays.append(pa.array(df[col].to_numpy().astype("datetime64[D]"), type=typ,
                                   from_pandas=True))
        else:
            arrays.append(pa.Array.from_pandas(df[col], type=typ))
    return pa.Table.from_arrays(arrays, names=COLUMNS)


def write_tape(df: pd.DataFrame, out_dir: Path = DEFAULT_OUT_DIR) -> tuple[Path, Path]:
    """Write loan_tape.parquet and loan_tape.csv; return both paths.

    TECH: both files come from the same Arrow table, so they hold identical values.
      CSV writes decimals with 2 places, dates as YYYY-MM-DD and nulls as blanks.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    table = to_arrow(df)
    parquet_path, csv_path = out_dir / "loan_tape.parquet", out_dir / "loan_tape.csv"
    pq.write_table(table, parquet_path)
    pa_csv.write_csv(table, csv_path)
    return parquet_path, csv_path


def parse_args(argv: Sequence[str] | None, cfg: Config) -> argparse.Namespace:
    """Command-line options. TECH: argparse; defaults come from the config."""
    run = cfg["run"]
    parser = argparse.ArgumentParser(description="Generate the LoanIQ synthetic loan tape.")
    parser.add_argument("--n", type=int, default=run["n_default"], help="number of loans")
    parser.add_argument("--seed", type=int, default=run["seed_default"], help="random seed")
    parser.add_argument("--as-of", default=run["as_of_default"],
                        help="tape cut-off date, 1st of a month (YYYY-MM-01)")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="output folder")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for `python -m app.loan_tape_gen`. Returns the exit code.

    TECH: prints a one-screen summary so you can sanity-check the tape at a glance.
    """
    cfg = load_config()
    args = parse_args(argv, cfg)
    df = generate_tape(n=args.n, seed=args.seed, as_of=args.as_of, cfg=cfg)
    parquet_path, csv_path = write_tape(df, args.out_dir)
    dq_rate = (df["dq_status"] != "Current").mean()
    print(f"Wrote {len(df):,} loans (seed {args.seed}, as of {args.as_of})")
    print(f"  {parquet_path}\n  {csv_path}")
    print(f"  Delinquent: {dq_rate:.1%}   Total current UPB: ${df['current_upb'].sum():,.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
