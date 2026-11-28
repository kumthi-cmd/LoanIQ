"""SIFMA's TBA settlement calendar and the rolling Current month (Step 6b).

Where it sits:
    config/pricing.toml [settlement] -> [load_calendar] -> Calendar
    New York date -> [roll_for] -> Roll (Current month, next month, days between)
    -> model.py prices Current and the drop to the next month

BUSINESS: a TBA trade is for delivery in a month, on the settlement date SIFMA
  publishes for the product's class (Class A 30-year UMBS, Class B 15-year UMBS and
  Ginnie Mae, Class C 30-year Ginnie Mae). Two business days before settlement is
  the 48-hour notification date, when the seller names the pools it will deliver.
  After that day the month is allocated, so the desk quotes the next one: Current
  is the first month whose notification date is today or later. Today
  (2026-11-27) that is December 2026 for every class; on 2026-12-09 Class A
  (notified 12-08) has rolled to January while Classes B and C are still December.
TECH:
  - The dates are TOML dates in pricing.toml, read by tomllib as datetime.date.
    Months must be consecutive ("2026-11", "2026-12", "2027-01", ...) and each
    notification must come before its settlement, or the app does not start.
  - Pure functions of (calendar, date); the caller passes the New York date.
  - Past the end of the list, roll_for raises CalendarExhausted (HTTP 503 in the
    API) rather than quote a month it has no dates for. A test fails months
    earlier (min_months_ahead), as the reminder to copy in SIFMA's next year.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


class CalendarExhausted(LookupError):
    """No SIFMA dates left for today's Current month and the one after."""


@dataclass(frozen=True)
class SettlementMonth:
    """One delivery month for one class.

    BUSINESS: e.g. Class A, December 2026: notification 2026-12-08, settlement 2026-12-10.
    TECH: month is the first day of the delivery month.
    """
    month: date
    notification: date
    settlement: date

    @property
    def label(self) -> str:
        """The desk's name for the month: "Dec 2026"."""
        return self.month.strftime("%b %Y")


@dataclass(frozen=True)
class Roll:
    """What a class quotes today: Current, the month after, and days between.

    BUSINESS: days is from Current's settlement date to the next month's, the
      period a holder finances the bonds when rolling (the drop, model.py).
    """
    sifma_class: str
    current: SettlementMonth
    next: SettlementMonth

    @property
    def days(self) -> int:
        """Calendar days between the two settlement dates."""
        return (self.next.settlement - self.current.settlement).days


# TECH: class -> its months in date order.
Calendar = dict[str, tuple[SettlementMonth, ...]]


def parse_month(key: str, cls: str) -> date:
    """ "2026-12" -> date(2026, 12, 1). TECH: anything else is a config error."""
    try:
        year, month = key.split("-")
        return date(int(year), int(month), 1)
    except ValueError as err:
        raise ValueError(f"Pricing settlement {cls}: month {key!r} must be YYYY-MM") from err


def next_month(day: date) -> date:
    """The first day of the month after `day`'s month."""
    return date(day.year + day.month // 12, day.month % 12 + 1, 1)


def load_class(cls: str, raw: Any) -> tuple[SettlementMonth, ...]:
    """One class's months, checked.

    BUSINESS: a gap or a notification after its settlement is a copying error
      from SIFMA's calendar, and stops the app.
    """
    if not isinstance(raw, dict) or not raw:
        raise ValueError(f"Pricing settlement {cls}: needs at least one month")
    months = []
    for key, entry in raw.items():
        if not isinstance(entry, dict) or set(entry) != {"notification", "settlement"} \
                or not all(isinstance(entry[k], date) for k in entry):
            raise ValueError(f"Pricing settlement {cls} {key}: needs notification and settlement dates")
        months.append(SettlementMonth(parse_month(key, cls), entry["notification"], entry["settlement"]))
    months.sort(key=lambda m: m.month)
    for prev, cur in zip(months, months[1:]):
        if cur.month != next_month(prev.month):
            raise ValueError(f"Pricing settlement {cls}: no dates for the month after {prev.label}")
    for m in months:
        if not m.notification < m.settlement:
            raise ValueError(f"Pricing settlement {cls} {m.label}: notification must come before settlement")
    return tuple(months)


def load_calendar(raw: dict[str, Any]) -> tuple[Calendar, int]:
    """[settlement] -> (class -> months, min_months_ahead)."""
    ahead = raw.get("min_months_ahead")
    if isinstance(ahead, bool) or not isinstance(ahead, int) or ahead < 2:
        raise ValueError("Pricing settlement: min_months_ahead must be a whole number, 2 or more")
    return {cls: load_class(cls, v) for cls, v in raw.items() if cls != "min_months_ahead"}, ahead


def roll_for(calendar: Calendar, cls: str, today: date) -> Roll:
    """Today's Current month for one class, and the month after it.

    BUSINESS: Current is the first month whose notification date is today or
      later; it rolls the day after the notification date.
    TECH: raises CalendarExhausted when Current or the month after is missing.
    """
    months = calendar[cls]
    for i, m in enumerate(months):
        if today <= m.notification:
            if i + 1 < len(months):
                return Roll(cls, m, months[i + 1])
            break
    raise CalendarExhausted(f"SIFMA Class {cls} has no settlement dates after {today}; "
                            "copy the next year into pricing.toml")


def months_ahead(calendar: Calendar, cls: str, today: date) -> int:
    """How many months, Current included, still have dates.

    BUSINESS: the run-out test needs at least min_months_ahead.
    """
    return sum(1 for m in calendar[cls] if today <= m.notification)
