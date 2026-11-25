"""Product slotting: which agency pool and coupons each loan can go into, and its spec stories.

Where it sits:
    loan tape (DuckDB `loans`) -> [slotting: POST /api/slotting/run] -> `slots` table
    -> Loan Tape columns Slot and Spec Stories, and the loan hover card
    -> best execution (Step 6) prices each slot

BUSINESS:
    Before a desk can price a tape it has to slot it: for every loan, decide whether
    an agency pool will take it (UMBS or GNMA II), at which pass-through coupons (a
    down and an up coupon from its note rate), and which spec stories it carries
    (low loan balance, New York, Puerto Rico, low FICO). Loans that fail a check are
    "not slotted", with the reason. All rules are illustrative: the agency map,
    products, status and coupon rule are in config/slotting.toml, the stories in
    config/spec_stories.toml, the sources in docs/public-sources.md, and worked
    examples in docs/domain/slotting-rules.md.

TECH:
    - One pass: a single CREATE TABLE ... AS SELECT (slots_sql) slots every loan into
      a staging table. Every value from config (programs, statuses, the strip, story
      names) goes in as a named parameter ($p0, $p1, ...); the only SQL inlined is
      each spec story's validated rule (spec_stories.validate_where).
    - The run is a generator (SlottingRun.events): it yields one step event as each
      step finishes, with real counts queried from the staging table. The server
      never sleeps; the screen paces the commentary (docs/decisions.md).
    - Publish is one transaction that swaps the staging table into `slots` and
      rebuilds the view `loans_slotted` (the tape plus two text columns), so a
      reader sees the old result or the new one, never half of each. A run that is
      stopped early (the visitor closes the stream) drops its staging table and
      leaves the last result untouched.
    - Coupons are exact: the note rate is turned into whole units of 0.0001% and
      rounded down with integer arithmetic, because DuckDB divides DECIMALs as
      binary floating point.
"""

from __future__ import annotations

import json
import string
import tomllib
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb

from app.spec_stories import SPEC_STORIES_PATH, Story, cap_label, load_spec_stories

CONFIG_DIR = Path(__file__).resolve().parent / "config"
SLOTTING_PATH = CONFIG_DIR / "slotting.toml"
WORDS_PATH = Path(__file__).resolve().parents[2] / "content" / "slotting.json"

# TECH: LoanIQ's own table names, constants, never user input.
STAGING, SLOTS, GRID_VIEW = "slots_staging", "slots", "loans_slotted"
# TECH: the two columns the Loan Tape gains once a run exists, with their DuckDB type.
GRID_COLUMNS = {"slot": "VARCHAR", "spec_stories": "VARCHAR"}

# BUSINESS: why a loan is not slotted, in the order the checks run. The codes key the
#   words in content/slotting.json "reasons".
NO_AGENCY, NO_TBA_PRODUCT, NOT_CURRENT = "no_agency", "product", "status"
REASONS = (NO_AGENCY, NO_TBA_PRODUCT, NOT_CURRENT)
# TECH: note rates and coupons are compared in whole units of 0.0001 percent.
UNITS = 10_000
TOP_KEYS = {"agencies", "products", "status", "coupons"}
NO_POOL = "none"  # TECH: the [agencies] key for programs with no agency pool


# =============================================================================
# The rules, as loaded from slotting.toml
# =============================================================================

@dataclass(frozen=True)
class SlottingRules:
    """Every rule slotting applies, validated.

    BUSINESS: agencies maps program -> agency ("FHA" -> "GNMA II"); a program in
      no_agency has no pool. terms maps an eligible product -> its term label
      ("30Y Fixed" -> "30Y"). min_strip and step are in percent.
    TECH: Decimals, exact. programs and products are every name the tape can hold
      (the generator's config), in config order, used to order commentary.
      stories are spec_stories.toml's, tiers expanded, in config order.
    """
    agencies: dict[str, str]
    no_agency: tuple[str, ...]
    terms: dict[str, str]
    eligible_status: str
    min_strip: Decimal
    step: Decimal
    stories: tuple[Story, ...]
    programs: tuple[str, ...] = ()
    products: tuple[str, ...] = ()

    @property
    def agency_names(self) -> list[str]:
        """BUSINESS: the agencies in config order (UMBS, then GNMA II)."""
        return list(dict.fromkeys(self.agencies.values()))

    @property
    def coupon_scale(self) -> int:
        """TECH: decimals a coupon needs: 0.5 -> 1, 0.25 -> 2 (at least 1)."""
        return max(1, -self.step.normalize().as_tuple().exponent)

    def families(self) -> dict[str, list[Story]]:
        """BUSINESS: stories grouped by family (LLB, NY, ...), tiers from the lowest cap up."""
        out: dict[str, list[Story]] = {}
        for s in self.stories:
            out.setdefault(s.family, []).append(s)
        return {k: sorted(v, key=lambda s: s.cap or 0) for k, v in out.items()}


def percent(raw: dict[str, Any], key: str, minimum_exclusive: bool) -> Decimal:
    """A percent from [coupons], exact. TECH: must be a number, > 0 or >= 0."""
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Slotting coupons: {key} must be a number (percent)")
    number = Decimal(str(value))
    if number < 0 or (minimum_exclusive and number == 0):
        raise ValueError(f"Slotting coupons: {key} must be {'above' if minimum_exclusive else 'at least'} 0")
    return number


def load_agencies(raw: dict[str, Any], programs: Sequence[str]) -> tuple[dict[str, str], tuple[str, ...]]:
    """[agencies] -> (program -> agency, programs with no pool), checked.

    BUSINESS: every program the tape can hold must be in exactly one list, so no
      loan is left out by accident.
    """
    by_program: dict[str, str] = {}
    for agency, members in raw.items():
        if not isinstance(members, list) or not members:
            raise ValueError(f"Slotting agencies: {agency} must list at least one program")
        for program in members:
            if program in by_program:
                raise ValueError(f"Slotting agencies: {program} is in two lists")
            by_program[program] = agency
    if programs and set(by_program) != set(programs):
        raise ValueError(f"Slotting agencies: unknown {sorted(set(by_program) - set(programs))}, "
                         f"missing {sorted(set(programs) - set(by_program))}")
    pools = {p: a for p, a in by_program.items() if a != NO_POOL}
    return pools, tuple(p for p, a in by_program.items() if a == NO_POOL)


def load_terms(raw: dict[str, Any], products: Sequence[str]) -> dict[str, str]:
    """[products] -> product -> term label, checked against the tape's products."""
    if not raw or not all(isinstance(v, str) and v for v in raw.values()):
        raise ValueError("Slotting products: list at least one product, each with a term label")
    if products and set(raw) - set(products):
        raise ValueError(f"Slotting products: unknown {sorted(set(raw) - set(products))}")
    return dict(raw)


def load_slotting_rules(columns: Sequence[str], programs: Sequence[str] = (),
                        products: Sequence[str] = (), path: Path = SLOTTING_PATH,
                        stories_path: Path = SPEC_STORIES_PATH) -> SlottingRules:
    """Load and validate slotting.toml, plus the spec stories it reads.

    BUSINESS: the single entry point; if any rule is wrong the app does not start,
      rather than mis-slotting loans.
    TECH: columns are the tape's columns (the allow-list for story rules); programs
      and products are the names the tape can hold (empty = not checked, for small
      test configs). Raises ValueError naming the bad rule.
    """
    with path.open("rb") as f:
        raw = tomllib.load(f)
    if set(raw) != TOP_KEYS:
        raise ValueError(f"Slotting: sections must be exactly {sorted(TOP_KEYS)}, got {sorted(raw)}")
    agencies, no_agency = load_agencies(raw["agencies"], programs)
    status = raw["status"].get("eligible")
    if not isinstance(status, str) or not status or set(raw["status"]) != {"eligible"}:
        raise ValueError("Slotting status: eligible must be one MBA status, e.g. \"Current\"")
    if set(raw["coupons"]) != {"min_strip_pct", "coupon_step_pct"}:
        raise ValueError("Slotting coupons: keys must be min_strip_pct and coupon_step_pct")
    stories = tuple(load_spec_stories(columns, products or None, path=stories_path))
    return SlottingRules(agencies, no_agency, load_terms(raw["products"], products), status,
                         percent(raw["coupons"], "min_strip_pct", False),
                         percent(raw["coupons"], "coupon_step_pct", True),
                         stories, tuple(programs), tuple(products))


def load_slotting_words(path: Path = WORDS_PATH) -> dict[str, Any]:
    """The visitor-facing words in content/slotting.json (templates, labels, reasons)."""
    return json.loads(path.read_text(encoding="utf-8"))


def story_labels(rules: SlottingRules, words: dict[str, Any]) -> dict[str, str]:
    """Display label for every story: LLB_275K -> "LLB 275K", LOW_FICO -> "Low FICO".

    TECH: a family missing from the words falls back to its config name.
    """
    out = {}
    for s in rules.stories:
        label = words["stories"].get(s.family, {}).get("label", s.family)
        out[s.name] = (words["slot"]["tier_label"].format(label=label, cap=cap_label(s.cap))
                       if s.cap is not None else label)
    return out


# =============================================================================
# The one-pass SQL
# =============================================================================

class Params:
    """Named query parameters for one SQL statement.

    TECH: DuckDB takes named parameters ($name) with a dict of values, so the order
      pieces of SQL are written in never has to match a list. add() stores a value
      and returns its placeholder ("$p3").
    """

    def __init__(self) -> None:
        self.values: dict[str, Any] = {}

    def add(self, value: Any) -> str:
        """Store one value; return the placeholder to write in the SQL."""
        key = f"p{len(self.values)}"
        self.values[key] = value
        return f"${key}"

    def many(self, values: Sequence[Any]) -> str:
        """"$p0, $p1, ..." for an IN (...) list."""
        return ", ".join(self.add(v) for v in values)


def agency_case(rules: SlottingRules, p: Params) -> str:
    """CASE WHEN program IN (...) THEN 'UMBS' ... END: the loan's agency, or NULL."""
    by_agency: dict[str, list[str]] = {}
    for program, agency in rules.agencies.items():
        by_agency.setdefault(agency, []).append(program)
    whens = " ".join(f"WHEN program IN ({p.many(progs)}) THEN {p.add(a)}" for a, progs in by_agency.items())
    return f"CASE {whens} END"


def term_case(rules: SlottingRules, p: Params) -> str:
    """CASE WHEN product = '30Y Fixed' THEN '30Y' ... END: the TBA term, or NULL."""
    return "CASE " + " ".join(f"WHEN product = {p.add(prod)} THEN {p.add(term)}"
                              for prod, term in rules.terms.items()) + " END"


def story_lists(rules: SlottingRules, labels: dict[str, str], p: Params) -> tuple[str, str]:
    """(story names list, story labels list) SQL for one loan.

    BUSINESS: one entry per family the loan fits. For a tiered family (LLB) the
      lowest tier the loan fits, so a $60K loan shows LLB 85K, not all nine tiers.
      A story applies only to the products it lists in spec_stories.toml.
    TECH: one CASE per family, tiers from the lowest cap up, so the first match is
      the tightest. list_filter(..., lambda x: x IS NOT NULL) drops families the
      loan does not fit; DuckDB's lambda syntax is "lambda x: <expression>".
    """
    names, shown = [], []
    for members in rules.families().values():
        products = p.many(members[0].products)
        names.append(f"CASE WHEN product IN ({products}) THEN CASE "
                     + " ".join(f"WHEN ({s.where}) THEN {p.add(s.name)}" for s in members) + " END END")
        shown.append(f"CASE WHEN product IN ({products}) THEN CASE "
                     + " ".join(f"WHEN ({s.where}) THEN {p.add(labels[s.name])}" for s in members) + " END END")
    keep = "lambda x: x IS NOT NULL"
    if not names:
        return "CAST([] AS VARCHAR[])", "CAST([] AS VARCHAR[])"
    return f"list_filter([{', '.join(names)}], {keep})", f"list_filter([{', '.join(shown)}], {keep})"


def template_sql(template: str, fields: dict[str, str], p: Params) -> str:
    """Turn a words template like "{agency} {term} {down} / {up}" into SQL concat(...).

    TECH: string.Formatter().parse splits the template into literal text (sent as
      parameters) and {field} names (each mapped to a SQL expression). An unknown
      field is a ValueError, so a typo in content/slotting.json fails at start-up.
    """
    parts = []
    for literal, name, _spec, _conv in string.Formatter().parse(template):
        if literal:
            parts.append(p.add(literal))
        if name is not None:
            if name not in fields:
                raise ValueError(f"Slotting words: unknown field {{{name}}} in {template!r}")
            parts.append(fields[name])
    return f"concat({', '.join(parts)})"


def slots_sql(rules: SlottingRules, words: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """The one pass: SELECT one slot row per loan from `loans`.

    BUSINESS (per loan, in this order; the first check that fails is the reason):
      1. agency  = the agency its program goes into     (none -> no_agency)
      2. term    = the TBA term of its product           (none -> product)
      3. current = its MBA status is the eligible status (no   -> status)
      If all pass, in percent:
        down_coupon = FLOOR((note_rate - min_strip) / step) x step
        up_coupon   = down_coupon + step
      e.g. note 3.125, strip 0.50, step 0.5: 2.625 -> down 2.5, up 3.0.
    TECH: the rounding runs on whole 0.0001% units (BIGINT), with a floored modulo
      ((x % s) + s) % s so it rounds down even below zero, then is cast back to an
      exact DECIMAL. Returns (sql, params); the grid text columns slot and
      spec_stories are built here too, from the words templates, so the grid can
      sort and filter them like any column.
    """
    p, scale = Params(), rules.coupon_scale
    labels = story_labels(rules, words)
    names, shown = story_lists(rules, labels, p)
    note = f"CAST(ROUND(note_rate * {UNITS}) AS BIGINT)"
    strip, step = p.add(int(rules.min_strip * UNITS)), p.add(int(rules.step * UNITS))
    coupon = f"DECIMAL({scale + 4}, {scale})"
    shorts = " ".join(f"WHEN {p.add(code)} THEN {p.add(words['reasons'][code]['short'])}" for code in REASONS)
    slot_text = template_sql(words["slot"]["slotted"], {
        "agency": "agency", "term": "term",
        "down": "CAST(down_coupon AS VARCHAR)", "up": "CAST(up_coupon AS VARCHAR)"}, p)
    sql = f"""
WITH s0 AS (SELECT *, {agency_case(rules, p)} AS agency, {term_case(rules, p)} AS term,
                  {note} - {strip} AS _x FROM loans),
s1 AS (SELECT *, CASE WHEN agency IS NULL THEN {p.add(NO_AGENCY)}
                      WHEN term IS NULL THEN {p.add(NO_TBA_PRODUCT)}
                      WHEN dq_status IS DISTINCT FROM {p.add(rules.eligible_status)} THEN {p.add(NOT_CURRENT)}
                 END AS reason FROM s0),
s2 AS (SELECT *, reason IS NULL AS eligible,
              CASE WHEN reason IS NULL THEN _x - ((_x % {step}) + {step}) % {step} END AS _down FROM s1),
s3 AS (SELECT *,
              CAST(CAST(_down AS DECIMAL(18,0)) * CAST(0.0001 AS DECIMAL(5,4)) AS {coupon}) AS down_coupon,
              CAST(CAST(_down + {step} AS DECIMAL(18,0)) * CAST(0.0001 AS DECIMAL(5,4)) AS {coupon}) AS up_coupon,
              CASE WHEN reason IS NULL THEN {names} ELSE CAST([] AS VARCHAR[]) END AS stories,
              CASE WHEN reason IS NULL THEN {shown} END AS _shown FROM s2)
SELECT loan_id, eligible, reason, agency, term, down_coupon, up_coupon, stories,
       CASE WHEN eligible THEN {slot_text} ELSE {p.add(words['slot']['not_slotted'])} END AS slot,
       CASE WHEN NOT eligible THEN CASE reason {shorts} END
            WHEN len(_shown) = 0 THEN {p.add(words['slot']['generic'])}
            ELSE array_to_string(_shown, ', ') END AS spec_stories
FROM s3
"""
    return sql, p.values


# =============================================================================
# The run: one pass, then a step event per check, then publish
# =============================================================================

@dataclass
class SlotEvent:
    """One server-sent event of a run. TECH: type is "step" or "done"; data is JSON."""
    type: str
    data: dict[str, Any]


def fmt(n: int) -> str:
    """BUSINESS: counts as a desk writes them: 1467 -> "1,467"."""
    return f"{n:,}"


def and_list(items: Sequence[str]) -> str:
    """["Jumbo", "Non-QM"] -> "Jumbo and Non-QM"; three or more -> "A, B and C"."""
    items = list(items)
    return " and ".join(items) if len(items) < 3 else f"{', '.join(items[:-1])} and {items[-1]}"


@dataclass
class SlottingRun:
    """One slotting run over the store's `loans` table.

    BUSINESS: the 13 steps a visitor watches on the default config: load, three
      eligibility checks, count, coupons, one step per spec-story family, overlaps,
      write. A new story family in spec_stories.toml adds one step by itself.
    TECH: events() is a generator: each step runs its query, then yields its event.
      totals collects every count for the done event and GET /api/slotting/status.
      on_publish (main.py) switches the Loan Tape to the new columns inside the same
      call that publishes, before the done event is sent.
    """
    con: duckdb.DuckDBPyConnection
    rules: SlottingRules
    words: dict[str, Any]
    on_publish: Callable[[], None] = lambda: None
    totals: dict[str, Any] = field(default_factory=dict)

    def plan(self) -> list[tuple[str, str | None]]:
        """The steps, in order: (kind, story family or None)."""
        stories = [("story", fam) for fam in self.rules.families()]
        return ([("load_tape", None), ("load_rules", None), ("agency", None), ("product", None),
                 ("status", None), ("eligible", None), ("coupons", None)]
                + stories + [("overlaps", None), ("write", None)])

    def events(self) -> Iterator[SlotEvent]:
        """Run every step, yielding a step event after each, then the done event.

        TECH: percent = step / steps x 100, rounded (13 steps: 8, 15, 23, ... 100).
          If the caller stops early (GeneratorExit), the finally drops the staging
          table and the last published result stays as it was.
        """
        plan, cur = self.plan(), self.con.cursor()
        try:
            for i, (kind, family) in enumerate(plan, start=1):
                name, line = self.run_step(cur, kind, family)
                yield SlotEvent("step", {"step": i, "steps": len(plan), "kind": kind, "name": name,
                                         "percent": round(100 * i / len(plan)), "line": line})
            yield SlotEvent("done", {"totals": self.totals})
        finally:
            cur.execute(f"DROP TABLE IF EXISTS {STAGING}")
            cur.close()

    def run_step(self, cur: duckdb.DuckDBPyConnection, kind: str, family: str | None) -> tuple[str, str]:
        """(step name, commentary line) for one step, after running its query."""
        if kind == "story":
            return self.story_step(cur, family or "")
        words = self.words["steps"][kind]
        values = getattr(self, f"step_{kind}")(cur)
        return words["name"], words["line"].format(**values)

    # -- the steps -------------------------------------------------------------
    # TECH: each returns the values its commentary template needs, and records the
    #   raw counts in self.totals.

    def step_load_tape(self, cur: duckdb.DuckDBPyConnection) -> dict[str, str]:
        """BUSINESS: how many loans are on the tape being slotted."""
        self.totals["loans"] = cur.execute("SELECT COUNT(*) FROM loans").fetchone()[0]
        return {"loans": fmt(self.totals["loans"])}

    def step_load_rules(self, _cur: duckdb.DuckDBPyConnection) -> dict[str, str]:
        """BUSINESS: the spec-story rules in force, all validated when the app started."""
        return {"rules": fmt(len(self.rules.stories)), "stories": fmt(len(self.rules.families()))}

    def step_agency(self, cur: duckdb.DuckDBPyConnection) -> dict[str, str]:
        """The one pass that writes the staging table, then the loans with no agency pool."""
        sql, params = slots_sql(self.rules, self.words)
        cur.execute(f"CREATE OR REPLACE TABLE {STAGING} AS {sql}", params)
        count, programs = self.reason_detail(cur, NO_AGENCY, "program", self.rules.programs)
        return {"count": count, "programs": and_list(programs)}

    def step_product(self, cur: duckdb.DuckDBPyConnection) -> dict[str, str]:
        """BUSINESS: agency loans whose product does not trade TBA (the ARMs)."""
        count, products = self.reason_detail(cur, NO_TBA_PRODUCT, "product", self.rules.products)
        return {"count": count, "products": ", ".join(products)}

    def step_status(self, cur: duckdb.DuckDBPyConnection) -> dict[str, str]:
        """BUSINESS: agency loans in a TBA product that are not current."""
        count, _ = self.reason_detail(cur, NOT_CURRENT, "dq_status", ())
        return {"count": count}

    def reason_detail(self, cur: duckdb.DuckDBPyConnection, reason: str, column: str,
                      order: Sequence[str]) -> tuple[str, list[str]]:
        """(count, distinct values of `column`) for the loans failing one check.

        TECH: column is one of three constants above, never user input. Values are
          put in `order` (config order), unknown ones last.
        """
        rows = cur.execute(f"SELECT l.{column}, COUNT(*) FROM {STAGING} s JOIN loans l USING (loan_id) "
                           "WHERE s.reason = ? GROUP BY 1", [reason]).fetchall()
        self.totals.setdefault("by_reason", {})[reason] = sum(n for _, n in rows)
        rank = {v: i for i, v in enumerate(order)}
        values = sorted((v for v, _ in rows), key=lambda v: (rank.get(v, len(rank)), v))
        return fmt(self.totals["by_reason"][reason]), values

    def step_eligible(self, cur: duckdb.DuckDBPyConnection) -> dict[str, str]:
        """BUSINESS: the loans that pass every check, by agency."""
        rows = dict(cur.execute(f"SELECT agency, COUNT(*) FROM {STAGING} WHERE eligible GROUP BY 1").fetchall())
        self.totals["by_agency"] = {a: rows.get(a, 0) for a in self.rules.agency_names}
        self.totals["slotted"] = sum(self.totals["by_agency"].values())
        self.totals["not_slotted"] = self.totals["loans"] - self.totals["slotted"]
        item = self.words["steps"]["eligible"]["by_agency_item"]
        parts = [item.format(count=fmt(n), agency=a) for a, n in self.totals["by_agency"].items()]
        return {"count": fmt(self.totals["slotted"]), "by_agency": ", ".join(parts)}

    def step_coupons(self, cur: duckdb.DuckDBPyConnection) -> dict[str, str]:
        """BUSINESS: the range of down and up coupons the slotted loans make, in percent."""
        row = cur.execute(f"SELECT MIN(down_coupon), MAX(down_coupon), MIN(up_coupon), MAX(up_coupon) "
                          f"FROM {STAGING} WHERE eligible").fetchone()
        keys = ("down_min", "down_max", "up_min", "up_max")
        self.totals["coupons"] = {k: (None if v is None else str(v)) for k, v in zip(keys, row)}
        return {k: v or "-" for k, v in self.totals["coupons"].items()}

    def story_step(self, cur: duckdb.DuckDBPyConnection, family: str) -> tuple[str, str]:
        """BUSINESS: how many slotted loans carry one spec-story family.

        TECH: list_has_any(stories, [tier names]) counts a loan once per family. For a
          tiered family the lowest tier's count is reported too ("55 of them the
          $85K tier"). The family's own words, if any, replace the generic ones.
        """
        members = self.rules.families()[family]
        own = self.words["stories"].get(family, {})
        label = own.get("label", family)
        tiered = members[0].cap is not None
        generic = self.words["steps"]["story_tiered" if tiered else "story"]
        count = cur.execute(f"SELECT COUNT(*) FROM {STAGING} WHERE list_has_any(stories, ?)",
                            [[s.name for s in members]]).fetchone()[0]
        self.totals.setdefault("stories", {})[family] = count
        values = {"label": label, "rule": members[0].where, "count": fmt(count)}
        if tiered:
            tiers = dict(cur.execute(f"SELECT s, COUNT(*) FROM (SELECT unnest(stories) AS s FROM {STAGING}) "
                                     "WHERE list_contains(?, s) GROUP BY 1",
                                     [[m.name for m in members]]).fetchall())
            self.totals.setdefault("tiers", {})[family] = {m.name: tiers.get(m.name, 0) for m in members}
            values.update(lowest_count=fmt(tiers.get(members[0].name, 0)),
                          lowest_cap=cap_label(members[0].cap or 0))
        name = own.get("step_name", generic["name"]).format(**values)
        return name, own.get("step_line", generic["line"]).format(**values)

    def step_overlaps(self, cur: duckdb.DuckDBPyConnection) -> dict[str, str]:
        """BUSINESS: loans that fit more than one story; they still go into one pool."""
        row = cur.execute(f"SELECT COUNT(*) FILTER (WHERE len(stories) > 1), "
                          f"COUNT(*) FILTER (WHERE eligible AND len(stories) = 0) FROM {STAGING}").fetchone()
        self.totals["multi_story"], self.totals["generic_tba"] = row
        self.totals["with_story"] = self.totals["slotted"] - self.totals["generic_tba"]
        return {"count": fmt(self.totals["multi_story"])}

    def step_write(self, cur: duckdb.DuckDBPyConnection) -> dict[str, str]:
        """Publish: swap the staging table into `slots` and rebuild the grid view.

        TECH: one transaction, so readers on other cursors see the old result or the
          new one. on_publish then points the Loan Tape at the view.
        """
        cur.execute("BEGIN TRANSACTION")
        try:
            cur.execute(f"CREATE OR REPLACE TABLE {SLOTS} AS SELECT * FROM {STAGING}")
            cur.execute(f"CREATE OR REPLACE VIEW {GRID_VIEW} AS SELECT l.*, s.slot, s.spec_stories "
                        f"FROM loans l LEFT JOIN {SLOTS} s USING (loan_id)")
            cur.execute(f"DROP TABLE {STAGING}")
            cur.execute("COMMIT")
        except duckdb.Error:
            cur.execute("ROLLBACK")
            raise
        self.on_publish()
        return {"slotted": fmt(self.totals["slotted"]), "generic": fmt(self.totals["generic_tba"])}
