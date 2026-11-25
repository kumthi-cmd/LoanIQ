"""Product slotting: which execution, product and coupon each loan can be sold into.

Where it sits:
    config/slotting.toml + config/spec_stories.toml -> [slotting]
    -> the `loans` table's slot columns (main.open_store, agent/tape_db)
    -> GET /api/loans/slotting and GET /api/slotting/rules -> Loan Tape (Step 5b)
    -> best execution (Step 6)

BUSINESS:
    Before a desk can price a tape it has to slot it: for every loan, decide whether
    an agency pool will take it, which execution (UMBS, Ginnie Mae II or whole
    loan) and product (UMBS 30, G2 30, ...) it belongs to, which pass-through
    coupons it can make, and which spec stories it carries. Step 6 then prices each
    slot and picks the best execution. All rules, fees and limits are illustrative
    and come from config/slotting.toml, with their sources in docs/public-sources.md.
    The rules, the formula and worked examples: docs/domain/slotting-rules.md.

TECH:
    - Rules are validated SQL tests (spec_stories.validate_where: tape columns,
      comparisons, AND / OR / NOT, IN, BETWEEN and literals only), so a bad rule
      stops the app when the config loads.
    - Slotting runs once, when the tape loads: create_slotted_table() copies the
      Parquet tape into a DuckDB table with nine extra columns (SLOT_COLUMNS). The
      grid's sorting, filtering and paging, and Ask the Tape's queries, then work on
      them unchanged, and nothing is recomputed per request.
    - Fees and the coupon step go into the SQL as named parameters ($p0, $p1, ...),
      as DECIMAL, so the coupon arithmetic is exact (no binary rounding of 0.19 or
      0.06). Note rates are multiples of 1/8 percent, exact in DECIMAL(8,4).
    - The rules' own SQL is the validated rendering from validate_where, never the
      raw config text, placed inside brackets in a CASE expression.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Sequence

import duckdb

from app.spec_stories import SPEC_STORIES_PATH, Story, load_spec_stories, validate_where

CONFIG_DIR = Path(__file__).resolve().parent / "config"
SLOTTING_PATH = CONFIG_DIR / "slotting.toml"
CONTENT_PATH = Path(__file__).resolve().parents[2] / "content" / "slotting.json"

# BUSINESS: the four outcomes of slotting, in the order a desk reads them.
AGENCY, WHOLE_LOAN, NOT_DELIVERABLE, UNSLOTTED = "Agency", "Whole loan", "Not deliverable", "Unslotted"
STATUS_ORDER = [AGENCY, WHOLE_LOAN, NOT_DELIVERABLE, UNSLOTTED]
# BUSINESS: why a loan is Unslotted: the config has no rule for it. The default
#   tape must have none (tests/test_slotting.py), so these flag a config gap.
NO_EXECUTION, NO_PRODUCT = "No execution rule", "No product rule"
PRICINGS = {"pass_through", "whole_loan"}

# TECH: the columns slotting adds to every loan, in this order, after the tape's own.
SLOT_COLUMNS = ["slot_status", "slot_reason", "execution", "slot_product", "net_rate",
                "base_coupon", "down_coupon", "up_coupon", "spec_stories"]


# =============================================================================
# The rules, as loaded from slotting.toml
# =============================================================================

@dataclass(frozen=True)
class NotDeliverable:
    """BUSINESS: a reason no agency pool will take the loan. TECH: where is validated SQL."""
    reason: str
    where: str
    source: str


@dataclass(frozen=True)
class Execution:
    """Where a loan can be sold, and that execution's fees.

    BUSINESS: min_spread_bps is the least the note rate must sit above the coupon:
      the servicer's minimum fee plus the guarantee fee.
    TECH: fees in bps (Decimal, exact). Whole-loan executions carry zeros and
      never get a coupon.
    """
    name: str
    where: str
    pricing: str
    servicing_min_bps: Decimal
    guarantee_fee_bps: Decimal
    max_spread_bps: Decimal
    max_buydown_bps: Decimal
    source: str
    fee_source: str | None

    @property
    def min_spread_bps(self) -> Decimal:
        """BUSINESS: minimum servicing + guarantee fee, in bps."""
        return self.servicing_min_bps + self.guarantee_fee_bps


@dataclass(frozen=True)
class Product:
    """BUSINESS: an agency product within one execution. TECH: tba gives a coupon ladder."""
    name: str
    execution: str
    where: str
    tba: bool
    source: str


@dataclass(frozen=True)
class SlottingRules:
    """Every rule slotting applies, validated. TECH: coupon_step_pct in percent."""
    coupon_step_pct: Decimal
    not_deliverable: tuple[NotDeliverable, ...]
    executions: tuple[Execution, ...]
    products: tuple[Product, ...]
    stories: tuple[Story, ...]


def bps(entry: dict[str, Any], key: str, name: str) -> Decimal:
    """A fee in bps from the config, as an exact Decimal. TECH: must be a number >= 0."""
    value = entry.get(key, 0)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"Slotting rule {name}: {key} must be a number of bps, 0 or more")
    return Decimal(str(value))


def check_keys(entry: dict[str, Any], required: set[str], optional: set[str], kind: str) -> str:
    """Refuse typos: every required key present, nothing unknown. Returns the rule's name."""
    name = str(entry.get("name") or entry.get("reason") or "<unnamed>")
    missing, unknown = required - set(entry), set(entry) - required - optional
    if missing or unknown:
        raise ValueError(f"Slotting {kind} {name}: missing {sorted(missing)}, unknown {sorted(unknown)}")
    return name


def rule_sql(entry: dict[str, Any], columns: Sequence[str], name: str) -> str:
    """A rule's `where`, validated. TECH: errors say "Slotting rule <name>: ..."."""
    return validate_where(entry["where"], columns, name, "Slotting rule")


def load_execution(entry: dict[str, Any], columns: Sequence[str], step: Decimal) -> Execution:
    """One [[execution]] table, checked.

    BUSINESS: a pass-through execution must leave room for its base coupon. The
      base coupon's spread is always at least the min spread and below min spread
      + one step, so max_spread_bps must be at least that, or some loans' base
      coupon would break the execution's own maximum.
    """
    fees = {"servicing_min_bps", "guarantee_fee_bps", "max_spread_bps", "max_buydown_bps", "fee_source"}
    name = check_keys(entry, {"name", "where", "pricing", "source"}, fees, "execution")
    if entry["pricing"] not in PRICINGS:
        raise ValueError(f"Slotting execution {name}: pricing must be one of {sorted(PRICINGS)}")
    amounts = [bps(entry, k, name) for k in
               ("servicing_min_bps", "guarantee_fee_bps", "max_spread_bps", "max_buydown_bps")]
    ex = Execution(name, rule_sql(entry, columns, name), entry["pricing"], *amounts,
                   entry["source"], entry.get("fee_source"))
    if ex.pricing == "pass_through" and ex.max_spread_bps < ex.min_spread_bps + step * 100:
        raise ValueError(f"Slotting execution {name}: max_spread_bps must be at least "
                         f"servicing + guarantee fee + one coupon step")
    return ex


def load_product(entry: dict[str, Any], columns: Sequence[str],
                 executions: dict[str, Execution]) -> Product:
    """One [[product]] table, checked: its execution exists and is pass-through."""
    name = check_keys(entry, {"name", "execution", "where", "tba", "source"}, set(), "product")
    ex = executions.get(entry["execution"])
    if ex is None or ex.pricing != "pass_through":
        raise ValueError(f"Slotting product {name}: execution {entry['execution']!r} "
                         f"is not a pass-through execution in slotting.toml")
    if not isinstance(entry["tba"], bool):
        raise ValueError(f"Slotting product {name}: tba must be true or false")
    return Product(name, ex.name, rule_sql(entry, columns, name), entry["tba"], entry["source"])


def load_slotting_rules(columns: Sequence[str], path: Path = SLOTTING_PATH,
                        stories_path: Path = SPEC_STORIES_PATH) -> SlottingRules:
    """Load and validate slotting.toml, plus the spec stories it reads.

    BUSINESS: the single entry point; if any rule is wrong, nothing loads and the
      app does not start, rather than mis-slotting loans.
    TECH: columns are the tape's own columns (the allow-list for every `where`).
      Raises ValueError (UnsafeWhereError included) naming the bad rule.
    """
    with path.open("rb") as f:
        raw = tomllib.load(f)
    step = Decimal(str(raw["coupons"]["coupon_step_pct"]))
    if step <= 0:
        raise ValueError("Slotting coupons: coupon_step_pct must be above 0")
    nd = tuple(NotDeliverable(r, rule_sql(e, columns, r), e["source"]) for e in raw.get("not_deliverable", [])
               for r in [check_keys(e, {"reason", "where", "source"}, set(), "not_deliverable")])
    execs = [load_execution(x, columns, step) for x in raw.get("execution", [])]
    by_name = {e.name: e for e in execs}
    products = tuple(load_product(p, columns, by_name) for p in raw.get("product", []))
    names = [r.reason for r in nd] + [e.name for e in execs] + [p.name for p in products]
    if len(names) != len(set(names)):
        raise ValueError(f"Slotting: duplicate rule names: {sorted({n for n in names if names.count(n) > 1})}")
    stories = tuple(load_spec_stories(columns, path=stories_path))
    return SlottingRules(step, nd, tuple(execs), products, stories)


def load_slot_labels(path: Path = CONTENT_PATH) -> dict[str, str]:
    """Grid headers for SLOT_COLUMNS, from content/slotting.json "labels"."""
    return json.loads(path.read_text(encoding="utf-8"))["labels"]


# =============================================================================
# The SQL that slots every loan
# =============================================================================

class Params:
    """Named query parameters for one SQL statement.

    TECH: DuckDB accepts named parameters ($name) with a dict of values, so the
      order in which pieces of SQL are written never has to match a list. add()
      stores a value and returns its placeholder ("$p3"). Rule labels, fees and
      the coupon step all go in this way; only validated rule SQL is inlined.
    """

    def __init__(self) -> None:
        self.values: dict[str, Any] = {}

    def add(self, value: Any) -> str:
        """Store one value; return the placeholder to write in the SQL."""
        key = f"p{len(self.values)}"
        self.values[key] = value
        return f"${key}"

    def pct(self, value: Decimal) -> str:
        """A percent value, exact, as DECIMAL(8,4) in the SQL."""
        return f"CAST({self.add(str(value))} AS DECIMAL(8,4))"


def first_match(cases: Sequence[tuple[str, str]], p: Params) -> str:
    """CASE WHEN (rule) THEN 'label' ... END: the first matching rule's label, or NULL.

    TECH: each `where` is validated SQL from the config; labels are parameters.
    """
    if not cases:
        return "CAST(NULL AS VARCHAR)"
    return "CASE " + " ".join(f"WHEN ({where}) THEN {p.add(label)}" for where, label in cases) + " END"


def fees_values(rules: SlottingRules, p: Params) -> str:
    """A VALUES table of each pass-through execution's spreads, in percent.

    BUSINESS (per execution, percent of balance a year):
      _min   = (servicing_min_bps + guarantee_fee_bps) / 100     the minimum spread
      _max   = max_spread_bps / 100                              the maximum spread
      _floor = (min spread in bps - max_buydown_bps) / 100       the lowest spread an
               up coupon may reach by buying down the guarantee fee
    TECH: whole-loan executions are left out, so their loans join to NULL fees.
    """
    rows = [f"({p.add(ex.name)}, {p.pct(ex.min_spread_bps / 100)}, {p.pct(ex.max_spread_bps / 100)}, "
            f"{p.pct((ex.min_spread_bps - ex.max_buydown_bps) / 100)})"
            for ex in rules.executions if ex.pricing == "pass_through"]
    if not rows:
        null = "CAST(NULL AS DECIMAL(8,4))"
        rows = [f"(CAST(NULL AS VARCHAR), {null}, {null}, {null})"]
    return f"SELECT * FROM (VALUES {', '.join(rows)}) AS f(_fee_execution, _min, _max, _floor)"


def product_cases(rules: SlottingRules, p: Params) -> tuple[str, str]:
    """(product name, TBA flag): the first product rule within the loan's execution."""
    if not rules.products:
        return "CAST(NULL AS VARCHAR)", "FALSE"
    name = "CASE " + " ".join(f"WHEN _execution = {p.add(x.execution)} AND ({x.where}) THEN {p.add(x.name)}"
                              for x in rules.products) + " END"
    tba = [x.name for x in rules.products if x.tba]
    flag = f"COALESCE(_product IN ({', '.join(p.add(n) for n in tba)}), FALSE)" if tba else "FALSE"
    return name, flag


def stories_sql(rules: SlottingRules, p: Params) -> str:
    """The loan's spec stories as text, e.g. "LLB_110K, NY", or NULL for none.

    BUSINESS: only a TBA agency loan carries spec stories (the caller checks),
      and only for the tape products each story lists. For a tiered family (LLB)
      the tightest tier the loan fits is shown: an $80K loan fits every LLB tier,
      and the $85K tier is the one a desk quotes first (docs/decisions.md).
    TECH: one CASE per family, tiers in increasing cap order, so the first match
      is the tightest; concat_ws skips NULLs; NULLIF turns "" (no story) into NULL.
    """
    families: dict[str, list[Story]] = {}
    for s in rules.stories:
        families.setdefault(s.family, []).append(s)
    pieces = []
    for members in families.values():
        members.sort(key=lambda s: s.cap or 0)
        products = ", ".join(p.add(x) for x in members[0].products)
        pieces.append(f"CASE WHEN product IN ({products}) THEN "
                      f"{first_match([(s.where, s.name) for s in members], p)} END")
    if not pieces:
        return "CAST(NULL AS VARCHAR)"
    return f"NULLIF(concat_ws(', ', {', '.join(pieces)}), '')"


def slotted_select(rules: SlottingRules) -> tuple[str, dict[str, Any]]:
    """SELECT every tape column plus SLOT_COLUMNS, from read_parquet($path).

    BUSINESS (per loan, in this order):
      1. a not-deliverable rule matches -> Not deliverable, with its reason
      2. else the first execution rule -> UMBS, Ginnie Mae II or Whole loan
      3. a pass-through execution -> the first product rule within it
      4. a TBA product -> coupons, in percent:
           net_rate    = note_rate - min spread
           base_coupon = FLOOR(net_rate / step) x step
           down_coupon = base - step, kept if note_rate - down <= max spread
           up_coupon   = base + step, kept if note_rate - up   >= floor spread
         e.g. UMBS (min 0.75, max 2.50, floor 0.50), note 6.875: net 6.125, base
         6.0, down 5.5 (spread 1.375), up 6.5 (spread 0.375 < 0.50): no up coupon.
    TECH: returns (sql, params); the caller adds params["path"], the Parquet file.
      Helper columns start with "_" and are dropped with DuckDB's
      SELECT * EXCLUDE (...), which keeps every tape column in tape order.
    """
    p = Params()
    step = p.pct(rules.coupon_step_pct)
    product, tba = product_cases(rules, p)
    whole = [e.name for e in rules.executions if e.pricing == "whole_loan"]
    is_whole = f"_execution IN ({', '.join(p.add(n) for n in whole)})" if whole else "FALSE"
    agency, wl, nd, un = (p.add(s) for s in (AGENCY, WHOLE_LOAN, NOT_DELIVERABLE, UNSLOTTED))
    note = "CAST(note_rate AS DECIMAL(8,4))"
    sql = f"""
WITH src AS (SELECT * FROM read_parquet($path)),
fees AS ({fees_values(rules, p)}),
s1 AS (SELECT *, {first_match([(r.where, r.reason) for r in rules.not_deliverable], p)} AS _nd,
              {first_match([(e.where, e.name) for e in rules.executions], p)} AS _rule FROM src),
s2 AS (SELECT *, CASE WHEN _nd IS NULL THEN _rule END AS _execution FROM s1),
s3 AS (SELECT s2.*, fees.* FROM s2 LEFT JOIN fees ON fees._fee_execution = s2._execution),
s4 AS (SELECT *, CASE WHEN _min IS NOT NULL THEN {product} END AS _product FROM s3),
s5 AS (SELECT *, {tba} AS _tba,
           CASE WHEN _nd IS NOT NULL THEN {nd}
                WHEN _execution IS NULL THEN {un}
                WHEN {is_whole} THEN {wl}
                WHEN _product IS NULL THEN {un}
                ELSE {agency} END AS _status FROM s4),
s6 AS (SELECT *, CASE WHEN _status = {agency} AND _tba THEN {note} - _min END AS _net FROM s5),
s7 AS (SELECT *, FLOOR(_net / {step}) * {step} AS _base FROM s6)
SELECT * EXCLUDE (_nd, _rule, _execution, _fee_execution, _min, _max, _floor, _product, _tba,
                  _status, _net, _base),
    _status AS slot_status,
    CASE WHEN _nd IS NOT NULL THEN _nd
         WHEN _status = {un} AND _execution IS NULL THEN {p.add(NO_EXECUTION)}
         WHEN _status = {un} THEN {p.add(NO_PRODUCT)} END AS slot_reason,
    CASE WHEN _status IN ({agency}, {wl}) THEN _execution END AS execution,
    CASE WHEN _status = {agency} THEN _product END AS slot_product,
    CAST(_net AS DECIMAL(8,4)) AS net_rate,
    CAST(_base AS DECIMAL(6,3)) AS base_coupon,
    CAST(CASE WHEN {note} - (_base - {step}) <= _max THEN _base - {step} END AS DECIMAL(6,3)) AS down_coupon,
    CAST(CASE WHEN {note} - (_base + {step}) >= _floor THEN _base + {step} END AS DECIMAL(6,3)) AS up_coupon,
    CASE WHEN _status = {agency} AND _tba THEN {stories_sql(rules, p)} END AS spec_stories
FROM s7
"""
    return sql, p.values


def create_slotted_table(con: duckdb.DuckDBPyConnection, parquet_path: Path, rules: SlottingRules,
                         table: str = "loans") -> None:
    """Copy the Parquet tape into `table`, with every loan slotted.

    BUSINESS: the one place slotting runs. The grid's tape and Ask the Tape's
      read-only copy both call it, so they always agree.
    TECH: CREATE TABLE ... AS SELECT with named parameters. `table` is LoanIQ's
      own constant ("loans"), never user input.
    """
    sql, params = slotted_select(rules)
    con.execute(f"CREATE TABLE {table} AS {sql}", {**params, "path": str(parquet_path)})


def parquet_columns(con: duckdb.DuckDBPyConnection, parquet_path: Path) -> list[str]:
    """The tape's own column names, in file order. TECH: DESCRIBE reads only the schema."""
    rows = con.execute("DESCRIBE SELECT * FROM read_parquet(?)", [str(parquet_path)]).fetchall()
    return [r[0] for r in rows]
