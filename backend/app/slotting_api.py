"""The two slotting endpoints' responses: the slotting summary and the rules in force.

Where it sits:
    `loans` table slot columns (app/slotting.py) -> [slotting_api] -> main.py routes
    GET /api/loans/slotting   -> the Loan Tape's slotting panel (Step 5b)
    GET /api/slotting/rules   -> the read-only "Slotting rules" popup (Step 5b)

BUSINESS:
    The summary is the desk's first view of a slotted tape: how many loans and how
    much UPB fall into each execution, product and base coupon ("UMBS 30 6.0:
    212 loans, $68.4mm"), and how much cannot be delivered, and why. The rules
    response shows exactly which rules produced those numbers, so a visitor can
    check any loan's slot by hand. Both are read-only; rules change only in
    config/slotting.toml. All rules and numbers are illustrative.

TECH:
    - Pydantic models describe both responses, so FastAPI documents them and the
      front end's TypeScript types are generated from them (npm run gen:api).
    - The summary is one GROUP BY over the slot columns, with the same WHERE the
      grid uses (main.grid_where), then sorted in Python into the config's order
      (status, execution, product, coupon), which SQL alone does not know.
"""

from __future__ import annotations

from typing import Any

import duckdb
from pydantic import BaseModel

from app.slotting import STATUS_ORDER, SlottingRules


class SlotGroup(BaseModel):
    """One row of the slotting summary: loans with the same slot.

    BUSINESS: "Agency · UMBS · UMBS 30 · 6.0: 212 loans, $68.4mm, WAC 6.912".
      Not-deliverable rows carry their reason and no execution or coupon.
    TECH: current_upb in dollars; base_coupon and wac in percent; None where a
      slot has no such value (an ARM has no TBA coupon; a whole loan no product).
    """
    slot_status: str
    slot_reason: str | None
    execution: str | None
    slot_product: str | None
    base_coupon: float | None
    loans: int
    current_upb: float
    wac: float | None


class SlottingSummary(BaseModel):
    """GET /api/loans/slotting. TECH: totals are over the filtered loans; groups sorted."""
    loans: int
    current_upb: float
    groups: list[SlotGroup]


class NotDeliverableOut(BaseModel):
    """One not-deliverable rule. TECH: where is the validated SQL the engine runs."""
    reason: str
    where: str
    source: str


class ExecutionOut(BaseModel):
    """One execution and its fees. TECH: fees and spreads in bps (illustrative)."""
    name: str
    where: str
    pricing: str
    servicing_min_bps: float
    guarantee_fee_bps: float
    min_spread_bps: float
    max_spread_bps: float
    max_buydown_bps: float
    source: str
    fee_source: str | None


class ProductOut(BaseModel):
    """One product rule. TECH: tba true = gets the coupon ladder."""
    name: str
    execution: str
    where: str
    tba: bool
    source: str


class StoryOut(BaseModel):
    """One spec story (from spec_stories.toml). TECH: tiers are expanded (LLB_85K, ...)."""
    name: str
    family: str
    products: list[str]
    where: str


class SlottingRulesOut(BaseModel):
    """GET /api/slotting/rules: every rule slotting applies, in the order it applies them.

    BUSINESS: illustrative is always true: every rule, fee and limit is an
      illustrative choice traced to a public source, not a real desk's rules.
    TECH: coupon_step_pct in percent.
    """
    illustrative: bool
    coupon_step_pct: float
    not_deliverable: list[NotDeliverableOut]
    executions: list[ExecutionOut]
    products: list[ProductOut]
    spec_stories: list[StoryOut]


def rules_out(rules: SlottingRules) -> SlottingRulesOut:
    """The loaded rules as the API's response. TECH: Decimal fees become floats for JSON."""
    return SlottingRulesOut(
        illustrative=True,
        coupon_step_pct=float(rules.coupon_step_pct),
        not_deliverable=[NotDeliverableOut(reason=r.reason, where=r.where, source=r.source)
                         for r in rules.not_deliverable],
        executions=[ExecutionOut(name=e.name, where=e.where, pricing=e.pricing,
                                 servicing_min_bps=float(e.servicing_min_bps),
                                 guarantee_fee_bps=float(e.guarantee_fee_bps),
                                 min_spread_bps=float(e.min_spread_bps),
                                 max_spread_bps=float(e.max_spread_bps),
                                 max_buydown_bps=float(e.max_buydown_bps),
                                 source=e.source, fee_source=e.fee_source) for e in rules.executions],
        products=[ProductOut(name=p.name, execution=p.execution, where=p.where, tba=p.tba, source=p.source)
                  for p in rules.products],
        spec_stories=[StoryOut(name=s.name, family=s.family, products=list(s.products), where=s.where)
                      for s in rules.stories])


# BUSINESS: per slot, loans, current UPB in dollars, and the WAC (UPB-weighted note
#   rate, percent): sum(note_rate x current_upb) / sum(current_upb).
# TECH: {where} is main.grid_where's validated clause; its values stay parameters.
SLOTTING_SQL = """
SELECT slot_status, slot_reason, execution, slot_product, base_coupon,
       COUNT(*) AS loans,
       COALESCE(SUM(current_upb), 0) AS current_upb,
       ROUND(SUM(note_rate * current_upb) / NULLIF(SUM(current_upb), 0), 3) AS wac
FROM loans {where}
GROUP BY ALL
"""


def sort_key(row: tuple[Any, ...], rules: SlottingRules) -> tuple[Any, ...]:
    """Config order: status, then execution, product and reason as listed, then coupon.

    TECH: an unknown value (should not happen) sorts last; a NULL coupon first.
    """
    status, reason, execution, product, coupon = row[:5]
    def place(value: Any, order: list[str]) -> int:
        return order.index(value) if value in order else len(order)
    return (place(status, STATUS_ORDER), place(execution, [e.name for e in rules.executions]),
            place(product, [p.name for p in rules.products]),
            place(reason, [r.reason for r in rules.not_deliverable]),
            -1 if coupon is None else float(coupon))


def fetch_slotting(con: duckdb.DuckDBPyConnection, where_sql: str, params: list[Any],
                   rules: SlottingRules) -> SlottingSummary:
    """The slotting summary for the loans matching where_sql.

    BUSINESS: totals equal the grid's own count and UPB for the same filter.
    TECH: one aggregate query on a per-request cursor; DECIMAL becomes float.
    """
    cur = con.cursor()
    try:
        rows = cur.execute(SLOTTING_SQL.format(where=where_sql), params).fetchall()
    finally:
        cur.close()
    rows.sort(key=lambda r: sort_key(r, rules))
    groups = [SlotGroup(slot_status=r[0], slot_reason=r[1], execution=r[2], slot_product=r[3],
                        base_coupon=None if r[4] is None else float(r[4]), loans=r[5],
                        current_upb=float(r[6]), wac=None if r[7] is None else float(r[7])) for r in rows]
    return SlottingSummary(loans=sum(g.loans for g in groups),
                           current_upb=round(sum(g.current_upb for g in groups), 2), groups=groups)
