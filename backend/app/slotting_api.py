"""The Product Slotting routes: run it, ask whether it has run, and the loan hover card.

Where it sits:
    Loan Tape (Step 5b) -> [POST /api/slotting/run] -> slotting.SlottingRun -> SSE stream
    Loan Tape -> [GET /api/slotting/status] -> last run time and totals, or "not run"
    Loan Tape hover -> [GET /api/loans/{loan_id}/slots] -> coupons, stories and why

BUSINESS: a visitor clicks Product Slotting and watches the run: 13 steps, each with
  a commentary line carrying real counts, then the totals. Every visitor shares one
  result (same tape, same rules), so a second visitor sees the tape already slotted.
  Hovering a loan ID then explains where that loan can go, or why it cannot.
TECH:
  - Server-Sent Events, the same way POST /api/ask streams (app/agent/api.py): a
    route with response_class=EventSourceResponse that `yield`s ServerSentEvent
    objects. Event types: step (13 of them on the default config), done, error.
  - One run at a time: a threading.Lock. The dependency run_check refuses a run
    with HTTP 409 before streaming starts when one is going. The lock itself is
    taken inside the stream, and released in a finally, so a stream that never
    starts can never leave it held; a run that loses the race in between gets an
    error event instead of a 409.
  - The shared result lives in memory, like the tape: after a restart, status says
    not run and the Loan Tape has no slot columns until the next run.
  - Visitor-facing words come from content/slotting.json, filled with real values.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Annotated, Any

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel

from app.agent.tools import LOAN_ID_PATTERN
from app.slotting import SLOTS, SlottingRules, SlottingRun, story_labels
from app.spec_stories import cap_label

router = APIRouter()
log = logging.getLogger(__name__)


# =============================================================================
# Response models
# =============================================================================

class SlottingTotals(BaseModel):
    """The counts a finished run reports.

    BUSINESS: slotted + not_slotted = loans. by_agency: UMBS and GNMA II loans;
      by_reason: not-slotted loans by the first check they failed (no_agency,
      product, status); stories: slotted loans per story family (a loan can count in
      several); tiers: per LLB tier, loans whose lowest fitting tier it is;
      multi_story: loans with more than one story; generic_tba: slotted loans with
      none. coupons: the down and up coupon range, percent, as text ("1.5").
    """
    loans: int
    slotted: int
    not_slotted: int
    by_agency: dict[str, int]
    by_reason: dict[str, int]
    stories: dict[str, int]
    tiers: dict[str, dict[str, int]]
    with_story: int
    generic_tba: int
    multi_story: int
    coupons: dict[str, str | None]


class SlottingStatus(BaseModel):
    """GET /api/slotting/status. TECH: run_at is UTC; totals null until a run finishes."""
    run: bool
    running: bool
    run_at: datetime | None = None
    totals: SlottingTotals | None = None


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


# =============================================================================
# The shared result
# =============================================================================

@dataclass
class SlottingService:
    """Everything the routes need: the tape, the rules, the words and the last result.

    BUSINESS: one result for every visitor, because everyone sees the same tape.
    TECH: built in main.py's lifespan as app.state.slotting. on_publish is main's
      hook that switches the Loan Tape to the slotted view. run_at and totals are
      set only when a run publishes, so a run stopped early changes nothing.
    """
    con: duckdb.DuckDBPyConnection
    rules: SlottingRules
    words: dict[str, Any]
    on_publish: Callable[[], None] = lambda: None
    lock: threading.Lock = field(default_factory=threading.Lock)
    run_at: datetime | None = None
    totals: dict[str, Any] | None = None

    def stream(self) -> Iterator[ServerSentEvent]:
        """Run once, yielding each event as SSE; "error" if busy or if the run fails.

        TECH: lock.acquire(blocking=False) returns False at once instead of waiting.
          A threading.Lock may be released by another thread, which matters here:
          FastAPI may run each step of a sync generator on a different worker thread.
        """
        if not self.lock.acquire(blocking=False):
            yield ServerSentEvent(event="error", data={"message": self.words["errors"]["busy"]})
            return
        try:
            run = SlottingRun(self.con, self.rules, self.words)
            run.on_publish = lambda: self.publish(run.totals)
            for event in run.events():
                if event.type == "done":
                    event.data = self.status().model_dump(mode="json")
                yield ServerSentEvent(event=event.type, data=event.data)
        except (duckdb.Error, ValueError, KeyError):
            log.exception("Product Slotting run failed")
            yield ServerSentEvent(event="error", data={"message": self.words["errors"]["failed"]})
        finally:
            self.lock.release()

    def publish(self, totals: dict[str, Any]) -> None:
        """BUSINESS: the new result is live. TECH: called inside the write step."""
        self.totals, self.run_at = dict(totals), datetime.now(UTC)
        self.on_publish()

    def status(self) -> SlottingStatus:
        """BUSINESS: has slotting run on this tape, when, and with what totals."""
        if self.run_at is None or self.totals is None:
            return SlottingStatus(run=False, running=self.lock.locked())
        return SlottingStatus(run=True, running=self.lock.locked(), run_at=self.run_at,
                              totals=SlottingTotals(**self.totals))


def get_service(request: Request) -> SlottingService:
    """FastAPI dependency: the slotting service built at start-up (main.py lifespan)."""
    return request.app.state.slotting


Service = Annotated[SlottingService, Depends(get_service)]


def run_check(service: Service) -> SlottingService:
    """BUSINESS: one run at a time. TECH: HTTP 409 before the stream starts if busy."""
    if service.lock.locked():
        raise HTTPException(409, service.words["errors"]["busy"])
    return service


# =============================================================================
# Routes
# =============================================================================

@router.post("/api/slotting/run", response_class=EventSourceResponse)
def run_slotting(service: Annotated[SlottingService, Depends(run_check)]) -> Iterator[ServerSentEvent]:
    """BUSINESS: slot the whole tape, streaming each step with its counts.

    TECH: a plain (sync) generator; FastAPI runs it on a worker thread. The server
      does not pause between steps: on 2,000 loans the whole run takes a fraction
      of a second, and the screen paces the commentary for the visitor.
    """
    yield from service.stream()


@router.get("/api/slotting/status", response_model=SlottingStatus)
def slotting_status(service: Service) -> SlottingStatus:
    """BUSINESS: "Last run 11:42 AM" or "Not run on this tape". TECH: no query."""
    return service.status()


@router.get("/api/loans/{loan_id}/slots", response_model=LoanSlots)
def loan_slots(loan_id: str, service: Service) -> LoanSlots:
    """BUSINESS: the hover card for one loan ID on the Loan Tape.

    TECH: 400 for a malformed id (LN + 8 digits), 409 if slotting has not run, 404
      for an id not on this tape. The id goes in as a bound parameter.
    """
    if not LOAN_ID_PATTERN.match(loan_id):
        raise HTTPException(400, "A loan ID is LN followed by 8 digits")
    if service.run_at is None:
        raise HTTPException(409, "Product Slotting has not run on this tape yet")
    row = fetch_slot_row(service.con, loan_id)
    if row is None:
        raise HTTPException(404, f"No loan {loan_id} on this tape")
    return hover_card(row, service)


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


def hover_card(row: dict[str, Any], service: SlottingService) -> LoanSlots:
    """Build the card from one slot row and the words.

    BUSINESS: the loan's facts; for a slotted loan, its coupons, each story with its
      rule and why it fits, and the generic TBA line; otherwise the reason.
    TECH: money and rates go out as numbers (float); coupons as text, as stored.
    """
    loan = {c: (float(row[c]) if c in ("note_rate", "orig_upb") else row[c]) for c in CARD_FIELDS}
    base = dict(loan_id=row["loan_id"], run_at=service.run_at, slotted=row["eligible"], loan=loan,
                agency=row["agency"], term=row["term"], slot=row["slot"])
    if not row["eligible"]:
        return LoanSlots(**base, not_slotted=not_slotted(row, service.words))
    down, up = str(row["down_coupon"]), str(row["up_coupon"])
    card = service.words["card"]
    return LoanSlots(**base, down_coupon=down, up_coupon=up,
                     stories=story_fits(row, service.rules, service.words),
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
