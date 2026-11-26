"""The slot card: where one loan can go, or why it cannot, in the desk's words.

Where it sits:
    slots row (grid: slotting_api.fetch_slot_row; agent: row_from_agent) -> [slot_card]
    -> GET /api/loans/{loan_id}/slots (the Loan Tape's hover card)
    -> Ask the Tape's explain_slot tool (agent/tools.py, Step 5c)

BUSINESS: one card, built once, so the Loan Tape and Ask the Tape explain a loan the
  same way: its pool and coupons, each spec story with its rule and why it fits, and
  the generic TBA slot; or the plain-English reason it is not slotted.
TECH: moved out of slotting_api.py in Step 5c, so the agent's tools can use it
  without importing the routes. Words come from content/slotting.json.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import duckdb
from pydantic import BaseModel

from app.slotting import (NO_AGENCY, REASONS, SLOTS, SlottingRules, story_column, story_labels,
                          tier_column)
from app.spec_stories import cap_label


class StoryFit(BaseModel):
    """One spec story a loan fits. BUSINESS: rule is the SQL test; why is plain English."""
    name: str
    label: str
    rule: str
    why: str


class NotSlotted(BaseModel):
    """Why a loan is not slotted. TECH: reason is the code; short for the grid, text for the card."""
    reason: str
    short: str
    text: str


class LoanSlots(BaseModel):
    """GET /api/loans/{loan_id}/slots: the hover card.

    BUSINESS: the loan's own facts, its pool and coupons (percent, as text, e.g.
      "2.5"), every story it fits with the rule and the reason, and the generic TBA
      slot that is always open; or, if it is not slotted, why.
    """
    loan_id: str
    run_at: datetime
    slotted: bool
    loan: dict[str, Any]
    agency: str | None = None
    term: str | None = None
    slot: str
    down_coupon: str | None = None
    up_coupon: str | None = None
    stories: list[StoryFit] = []
    generic_tba: str | None = None
    generic_note: str | None = None
    not_slotted: NotSlotted | None = None


CARD_FIELDS = ["seller", "state", "program", "product", "note_rate", "orig_upb", "fico", "dq_status"]


def fetch_slot_row(con: duckdb.DuckDBPyConnection, loan_id: str) -> dict[str, Any] | None:
    """One loan's slot row joined to the tape fields the card shows, or None."""
    cur = con.cursor()
    try:
        cols = ", ".join(f"l.{c}" for c in CARD_FIELDS)
        result = cur.execute(f"SELECT s.*, {cols} FROM {SLOTS} s JOIN loans l USING (loan_id) "
                             "WHERE loan_id = ?", [loan_id])
        names = [d[0] for d in result.description]
        values = result.fetchone()
    finally:
        cur.close()
    return None if values is None else dict(zip(names, values))


def slot_card(row: dict[str, Any], rules: SlottingRules, words: dict[str, Any],
              run_at: datetime) -> LoanSlots:
    """Build the card from one slot row and the words.

    BUSINESS: the loan's facts; for a slotted loan, its coupons, each story with its
      rule and why it fits, and the generic TBA line; otherwise the reason. The Loan
      Tape's hover card and Ask the Tape's explain_slot tool both call this.
    TECH: row holds the slots-table fields (eligible, reason code, agency, term,
      slot, coupons, stories as a list of names) plus CARD_FIELDS. Money and rates go
      out as numbers (float); coupons as text, as stored.
    """
    loan = {c: (float(row[c]) if c in ("note_rate", "orig_upb") else row[c]) for c in CARD_FIELDS}
    base = dict(loan_id=row["loan_id"], run_at=run_at, slotted=row["eligible"], loan=loan,
                agency=row["agency"], term=row["term"], slot=row["slot"])
    if not row["eligible"]:
        return LoanSlots(**base, not_slotted=not_slotted(row, words))
    down, up = str(row["down_coupon"]), str(row["up_coupon"])
    card = words["card"]
    return LoanSlots(**base, down_coupon=down, up_coupon=up,
                     stories=story_fits(row, rules, words),
                     generic_tba=card["generic_tba"].format(agency=row["agency"], term=row["term"], down=down),
                     generic_note=card["generic_note"])


def story_fits(row: dict[str, Any], rules: SlottingRules, words: dict[str, Any]) -> list[StoryFit]:
    """BUSINESS: each story the loan carries, with its rule and the plain-English reason.

    TECH: the why template may use {orig_upb} (dollars, with commas), {fico} and
      {cap} (the tier, e.g. "275K").
    """
    by_name = {s.name: s for s in rules.stories}
    labels = story_labels(rules, words)
    out = []
    for name in row["stories"]:
        story = by_name[name]
        why = words["stories"].get(story.family, {}).get("why", "")
        out.append(StoryFit(name=name, label=labels[name], rule=story.where,
                            why=why.format(orig_upb=f"{row['orig_upb']:,.0f}", fico=row["fico"],
                                           cap=cap_label(story.cap) if story.cap else "")))
    return out


def not_slotted(row: dict[str, Any], words: dict[str, Any]) -> NotSlotted:
    """BUSINESS: why the loan is not slotted, in the card's words.

    TECH: a program can have its own sentence (by_program); else the template.
    """
    reason = words["reasons"][row["reason"]]
    text = reason.get("by_program", {}).get(row["program"]) or reason["text"].format(**row)
    return NotSlotted(reason=row["reason"], short=reason["short"], text=text)


def row_from_agent(flat: dict[str, Any], rules: SlottingRules, words: dict[str, Any]) -> dict[str, Any]:
    """Turn one row of the agent's flat slot columns back into a slots row for slot_card.

    BUSINESS: the agent's explain_slot answers from the same card as the hover, even
      though its copy holds slotting as flat columns (slotting.add_agent_columns).
    TECH: the reason code comes back from its short word; the stories from the
      story_<family> flags, a tiered family's member from its <family>_tier cap; the
      term from the product (slotting.toml [products]). Agency is kept for a loan
      that is not slotted only to name its program's pool, as the grid's row does.
    """
    code_of = {words["reasons"][c]["short"]: c for c in REASONS}
    reason = code_of.get(flat.get("not_slotted_reason") or "")
    stories = []
    for fam, members in rules.families().items():
        if not flat.get(story_column(fam)):
            continue
        if members[0].cap is None:
            stories.append(members[0].name)
        else:
            cap = flat.get(tier_column(fam))
            stories.append(next(m.name for m in members if m.cap == cap))
    agency = flat.get("agency")
    if agency is None and reason != NO_AGENCY:
        agency = rules.agencies.get(flat["program"])
    return {**flat, "eligible": bool(flat["deliverable"]), "reason": reason, "agency": agency,
            "term": rules.terms.get(flat["product"]) if flat["deliverable"] else None, "stories": stories}
