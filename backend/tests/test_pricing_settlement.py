"""Tests for SIFMA's settlement calendar and the rolling Current month (app/pricing/settlement.py).

BUSINESS: what a desk relies on when it quotes "Current":
  - Current is the next month whose 48-hour notification date has not passed; it
    rolls the day AFTER the notification date, per SIFMA class;
  - classes roll on different days (Class A first, then B, then C);
  - the December-to-January roll crosses the year end cleanly;
  - the dates copied from SIFMA are complete and in order, or the app stops;
  - the list does not quietly run out: a test fails months before it does.
TECH: pytest on the real pricing.toml calendar, plus small hand-written calendars
  for the config checks. The run-out test reads today's New York date on
  purpose: it is the yearly reminder to copy in SIFMA's next year.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.pricing.config import PRICING_PATH, load_pricing_config
from app.pricing.settlement import (CalendarExhausted, load_calendar, months_ahead, next_month,
                                    roll_for)
from tests.pricing_fixtures import pricing_config, slotting_rules

CFG = pricing_config()
CAL = CFG.calendar


def test_products_map_to_sifmas_classes() -> None:
    """BUSINESS: SIFMA's key: A = 30-year UMBS, B = 15-year UMBS and Ginnie Mae,
    C = 30-year Ginnie Mae. 20-year pools settle with Class B (no recorded source)."""
    classes = {p.name: p.sifma_class for p in CFG.products}
    assert classes == {"UMBS 30": "A", "UMBS 20": "B", "UMBS 15": "B",
                       "GNMA II 30": "C", "GNMA II 20": "B", "GNMA II 15": "B"}


def test_december_2026_dates_as_published() -> None:
    """BUSINESS: SIFMA's December 2026 dates, as published (spot check of the copy)."""
    dec = {cls: next(m for m in CAL[cls] if m.month == date(2026, 12, 1)) for cls in "ABC"}
    assert (dec["A"].notification, dec["A"].settlement) == (date(2026, 12, 8), date(2026, 12, 10))
    assert (dec["B"].notification, dec["B"].settlement) == (date(2026, 12, 11), date(2026, 12, 15))
    assert (dec["C"].notification, dec["C"].settlement) == (date(2026, 12, 15), date(2026, 12, 17))


def test_calendar_runs_november_2026_to_december_2027() -> None:
    """TECH: 14 consecutive months per class, as copied from SIFMA's 2026-2027 file."""
    for cls in "ABC":
        assert CAL[cls][0].month == date(2026, 11, 1) and CAL[cls][-1].month == date(2027, 12, 1)
        assert len(CAL[cls]) == 14


@pytest.mark.parametrize("cls, notification", [
    ("A", date(2026, 12, 8)), ("B", date(2026, 12, 11)), ("C", date(2026, 12, 15))])
def test_roll_the_day_after_notification(cls: str, notification: date) -> None:
    """BUSINESS: the day before and the day of the 48-hour notification date,
    Current is still December; the day after, the pools are allocated and Current
    is January."""
    before = date.fromordinal(notification.toordinal() - 1)
    after = date.fromordinal(notification.toordinal() + 1)
    assert roll_for(CAL, cls, before).current.label == "Dec 2026"
    assert roll_for(CAL, cls, notification).current.label == "Dec 2026"
    assert roll_for(CAL, cls, after).current.label == "Jan 2027"


def test_classes_roll_on_different_days() -> None:
    """BUSINESS: on 2026-12-09 Class A (notified 12-08) quotes January, while
    Classes B and C are still on December."""
    day = date(2026, 12, 9)
    assert [roll_for(CAL, c, day).current.label for c in "ABC"] == ["Jan 2027", "Dec 2026", "Dec 2026"]


def test_thanksgiving_is_december_for_everyone() -> None:
    """BUSINESS: on 2026-11-27 every class has passed November's notification
    date, so Current is December 2026 and the drop rolls into January 2027."""
    for cls in "ABC":
        roll = roll_for(CAL, cls, date(2026, 11, 27))
        assert (roll.current.label, roll.next.label) == ("Dec 2026", "Jan 2027")


def test_days_between_settlement_dates() -> None:
    """BUSINESS: the drop finances the bonds from Current's settlement to the next
    month's: Class A 2026-12-10 to 2027-01-14 = 35 days."""
    assert roll_for(CAL, "A", date(2026, 11, 27)).days == 35


def test_year_end_roll() -> None:
    """BUSINESS: after December 2026's notification Current is January 2027 and the
    drop rolls into February: the year changes cleanly."""
    roll = roll_for(CAL, "A", date(2026, 12, 9))
    assert (roll.current.month, roll.next.month) == (date(2027, 1, 1), date(2027, 2, 1))
    assert next_month(date(2026, 12, 1)) == date(2027, 1, 1)


def test_past_the_end_is_an_error_not_a_guess() -> None:
    """BUSINESS: after December 2027's notification there is no month after it to
    roll into; LoanIQ refuses to quote rather than invent SIFMA dates."""
    with pytest.raises(CalendarExhausted, match="Class A"):
        roll_for(CAL, "A", date(2027, 11, 11))   # Current would be Dec 2027, no Jan 2028
    assert roll_for(CAL, "A", date(2027, 11, 10)).current.label == "Nov 2027"


def test_sifma_calendar_has_months_left() -> None:
    """BUSINESS: the yearly reminder. Fails once fewer than min_months_ahead months
    (3) remain for any class, from about October 2027: copy SIFMA's next year
    from https://www.sifma.org/resources/general/mbs-notification-and-settlement-dates/
    into pricing.toml [settlement].
    TECH: deliberately uses today's New York date, not a fixed one."""
    today = datetime.now(UTC).astimezone(CFG.treasury.tz).date()
    for cls in CAL:
        assert months_ahead(CAL, cls, today) >= CFG.min_months_ahead, \
            f"SIFMA Class {cls} has fewer than {CFG.min_months_ahead} months of dates left"


def test_months_ahead_counts_current_and_later() -> None:
    """TECH: on 2027-10-01 Class A has Oct, Nov and Dec 2027 left: 3."""
    assert months_ahead(CAL, "A", date(2027, 10, 1)) == 3


# -----------------------------------------------------------------------------
# Config checks on the calendar
# -----------------------------------------------------------------------------

def calendar(months: dict[str, tuple[date, date]], ahead: int = 3) -> dict:
    """A one-class [settlement] table: "YYYY-MM" -> (notification, settlement)."""
    return {"min_months_ahead": ahead,
            "A": {k: {"notification": n, "settlement": s} for k, (n, s) in months.items()}}


@pytest.mark.parametrize("raw, reason", [
    (calendar({"2026-12": (date(2026, 12, 8), date(2026, 12, 10)),
               "2027-02": (date(2027, 2, 9), date(2027, 2, 11))}), "month after Dec 2026"),
    (calendar({"2026-12": (date(2026, 12, 10), date(2026, 12, 8))}), "before settlement"),
    (calendar({"Dec-26": (date(2026, 12, 8), date(2026, 12, 10))}), "YYYY-MM"),
    (calendar({"2026-12": (date(2026, 12, 8), date(2026, 12, 10))}, ahead=1), "min_months_ahead"),
    ({"min_months_ahead": 3, "A": {}}, "at least one month"),
    ({"min_months_ahead": 3, "A": {"2026-12": {"notification": date(2026, 12, 8)}}}, "notification and settlement"),
])
def test_bad_calendar_stops_the_app(raw: dict, reason: str) -> None:
    """BUSINESS: a copying slip from SIFMA's calendar (a skipped month, swapped
    dates, a typo) stops the app instead of quoting the wrong delivery month."""
    with pytest.raises(ValueError, match=reason):
        load_calendar(raw)


def test_product_class_must_have_dates(tmp_path: Path) -> None:
    """BUSINESS: a product on a class with no calendar could never be quoted."""
    text = PRICING_PATH.read_text(encoding="utf-8").replace('sifma_class = "C"', 'sifma_class = "D"', 1)
    path = tmp_path / "pricing.toml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="class 'D'"):
        load_pricing_config(slotting_rules(), path)
