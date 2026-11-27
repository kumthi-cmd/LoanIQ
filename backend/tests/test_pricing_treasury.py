"""Tests for the daily anchor: Treasury's par yield curve feed (app/pricing/treasury.py).

BUSINESS: the price file must always have a curve, and say how fresh it is:
  - today's curve is the latest one on or before today (on Thanksgiving, the
    Wednesday before; on the 1st of a month, last month's last business day);
  - it is fetched once per New York day, not once per visitor;
  - if Treasury is down, the last curve fetched is kept; with none, the recorded
    sample curve is used and the status says so;
  - an outage is not retried on every request.
TECH: no network. FakeTreasury (tests/pricing_fixtures.py) serves the recorded
  November 2026 month; Clock moves time. The real HTTPS fetch is tested with
  urllib.request.urlopen replaced by monkeypatch.
"""

from __future__ import annotations

import io
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.pricing import treasury
from app.pricing.treasury import (CurveCache, CurveError, fetch_curve, latest_on_or_before, month_url,
                                  parse_curve_xml, previous_month)
from tests.pricing_fixtures import (EMPTY_MONTH_XML, RECORDED_XML, Clock, FakeTreasury, pricing_config,
                                    utc)

CFG = pricing_config()
TENORS = CFG.anchor_tenors


def cache(fake: FakeTreasury, clock: Clock, **kw: object) -> CurveCache:
    """A CurveCache on the real [treasury] settings, the fake feed and the clock."""
    return CurveCache(CFG.treasury, TENORS, fake, clock, **kw)  # type: ignore[arg-type]


# -----------------------------------------------------------------------------
# Parsing the recorded feed
# -----------------------------------------------------------------------------

def test_recorded_month_parses() -> None:
    """BUSINESS: November 2026 has 17 business-day curves, 2026-11-02 to 11-25
    (the feed was recorded on Thanksgiving, 2026-11-26). The 10-year closed the
    25th at 4.85%."""
    curves = parse_curve_xml(RECORDED_XML)
    assert len(curves) == 17
    assert curves[0].curve_date == date(2026, 11, 2)
    assert curves[-1].curve_date == date(2026, 11, 25)
    assert curves[-1].yields["10Y"] == Decimal("4.85")
    assert curves[-1].yields["5Y"] == Decimal("4.65") and curves[-1].yields["7Y"] == Decimal("4.74")


def test_empty_month_has_no_curves() -> None:
    """BUSINESS: before the first business day's close, a month has no curve."""
    assert parse_curve_xml(EMPTY_MONTH_XML) == []


@pytest.mark.parametrize("day, expected", [
    (date(2026, 11, 26), date(2026, 11, 25)),   # Thanksgiving: Wednesday's curve
    (date(2026, 11, 29), date(2026, 11, 25)),   # Sunday after
    (date(2026, 11, 25), date(2026, 11, 25)),   # a business day uses its own curve
    (date(2026, 11, 3), date(2026, 11, 3)),
])
def test_latest_on_or_before(day: date, expected: date) -> None:
    """BUSINESS: weekends and holidays use the last business day's curve."""
    assert latest_on_or_before(parse_curve_xml(RECORDED_XML), day, TENORS).curve_date == expected


def test_no_curve_before_the_first_of_the_month() -> None:
    """TECH: nothing on or before 2026-11-01 in the November file."""
    assert latest_on_or_before(parse_curve_xml(RECORDED_XML), date(2026, 11, 1), TENORS) is None


def test_curve_missing_a_needed_tenor_is_skipped() -> None:
    """BUSINESS: a day with no 10-year yield cannot anchor UMBS 30, so the day
    before is used. TECH: the 25th's 10-year element is blanked."""
    body = RECORDED_XML.replace(
        b'<d:BC_10YEAR m:type="Edm.Double">4.85</d:BC_10YEAR>', b'<d:BC_10YEAR m:type="Edm.Double" m:null="true" />')
    assert latest_on_or_before(parse_curve_xml(body), date(2026, 11, 26), TENORS).curve_date == date(2026, 11, 24)


@pytest.mark.parametrize("body, reason", [
    (b"not xml at all", "not XML"),
    (b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><x>&a;</x>', "DOCTYPE"),
    (b"<feed>" + b" " * 3_000_000 + b"</feed>", "limit"),
])
def test_bad_replies_are_refused(body: bytes, reason: str) -> None:
    """TECH: a broken, oversized or entity-declaring reply is never parsed into a
    curve (entities are how "billion laughs" XML bombs work)."""
    with pytest.raises(CurveError, match=reason):
        parse_curve_xml(body)


def test_month_url() -> None:
    """TECH: the feed's documented query: data=... and field_tdr_date_value_month=YYYYMM."""
    url = month_url(CFG.treasury, date(2026, 11, 27))
    assert url.startswith("https://home.treasury.gov/")
    assert "data=daily_treasury_yield_curve" in url and "field_tdr_date_value_month=202611" in url


def test_previous_month() -> None:
    """TECH: across a year end too."""
    assert previous_month(date(2026, 12, 1)) == date(2026, 11, 1)
    assert previous_month(date(2027, 1, 15)) == date(2026, 12, 1)


def test_first_of_the_month_uses_last_months_curve() -> None:
    """BUSINESS: on 2026-12-01 December has no curve yet, so November 25th is used.
    TECH: the fake serves an empty December, then the recorded November."""
    fake = FakeTreasury()
    curve = fetch_curve(CFG.treasury, fake, date(2026, 12, 1), TENORS)
    assert curve.curve_date == date(2026, 11, 25)
    assert [u[-6:] for u in fake.urls] == ["202612", "202611"]


def test_no_curve_in_either_month_is_an_error() -> None:
    """TECH: two empty months -> CurveError, so the cache falls back."""
    with pytest.raises(CurveError, match="no curve"):
        fetch_curve(CFG.treasury, FakeTreasury({}), date(2026, 12, 1), TENORS)


# -----------------------------------------------------------------------------
# The cache: once a New York day, with fallbacks
# -----------------------------------------------------------------------------

def test_fetched_once_per_new_york_day() -> None:
    """BUSINESS: a hundred visitors on the same day cause one Treasury fetch."""
    fake, clock = FakeTreasury(), Clock(utc(2026, 11, 27, 15, 0))
    c = cache(fake, clock)
    first = c.get()
    for _ in range(5):
        assert c.get() is first
    assert first.status == "live" and first.curve.curve_date == date(2026, 11, 25)
    assert len(fake.urls) == 1


def test_new_york_midnight_starts_a_new_day() -> None:
    """BUSINESS: the day turns at midnight in New York, not at midnight UTC.
    TECH: 2026-11-28 03:00 UTC is still the 27th in New York (UTC-5), so no
      refetch; 05:30 UTC is the 28th, so one more fetch."""
    fake, clock = FakeTreasury(), Clock(utc(2026, 11, 27, 15, 0))
    c = cache(fake, clock)
    c.get()
    clock.now = utc(2026, 11, 28, 3, 0)
    c.get()
    assert len(fake.urls) == 1
    clock.now = utc(2026, 11, 28, 5, 30)
    c.get()
    assert len(fake.urls) == 2


def test_treasury_down_keeps_the_last_curve() -> None:
    """BUSINESS: yesterday's curve beats no curve. The status says "cached" so the
    label can say Treasury could not be reached."""
    fake, clock = FakeTreasury(), Clock(utc(2026, 11, 27, 15, 0))
    c = cache(fake, clock)
    live = c.get()
    fake.down, clock.now = True, utc(2026, 11, 28, 15, 0)
    stale = c.get()
    assert stale.status == "cached"
    assert stale.curve == live.curve and stale.fetched_at == live.fetched_at


def test_treasury_down_with_no_curve_uses_the_recorded_one() -> None:
    """BUSINESS: a server that never reached Treasury still shows prices, from
    the bundled curve, and says so (status "fixture", no fetch time)."""
    fake = FakeTreasury()
    fake.down = True
    result = cache(fake, Clock(utc(2026, 11, 27, 15, 0))).get()
    assert result.status == "fixture" and result.fetched_at is None
    assert result.curve.curve_date == date(2026, 11, 25)


def test_outage_is_not_retried_on_every_request() -> None:
    """BUSINESS: during an outage visitors should not each wait out the timeout.
    TECH: one attempt, then none until retry_minutes have passed, then one more;
      once Treasury is back, the next try is live again."""
    fake, clock = FakeTreasury(), Clock(utc(2026, 11, 27, 15, 0))
    fake.down = True
    c = cache(fake, clock)
    c.get()
    c.get()
    assert len(fake.urls) == 1
    clock.now += timedelta(minutes=CFG.treasury.retry_minutes - 1)
    c.get()
    assert len(fake.urls) == 1
    clock.now += timedelta(minutes=1)
    fake.down = False
    assert c.get().status == "live"
    assert len(fake.urls) == 2


def test_bad_xml_from_treasury_counts_as_down() -> None:
    """BUSINESS: a garbled reply must not break pricing; it falls back like an outage."""
    result = cache(FakeTreasury({"202611": b"<html>maintenance</html"}),
                   Clock(utc(2026, 11, 27, 15, 0))).get()
    assert result.status == "fixture"


def test_missing_fallback_file_is_an_error(tmp_path: Path) -> None:
    """TECH: an empty bundled file is a packaging bug, reported loudly."""
    empty = tmp_path / "curve.xml"
    empty.write_bytes(EMPTY_MONTH_XML)
    fake = FakeTreasury()
    fake.down = True
    with pytest.raises(CurveError, match="curve.xml"):
        cache(fake, Clock(utc(2026, 11, 27, 15, 0)), fallback_path=empty).get()


# -----------------------------------------------------------------------------
# The real HTTPS fetch, without the network
# -----------------------------------------------------------------------------

class FakeReply(io.BytesIO):
    """What urlopen returns: a readable body usable in `with`."""


def test_http_fetch_sends_timeout_and_caps_the_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """TECH: the fetch passes the config's timeout, names itself in User-Agent, and
    reads at most max_bytes + 1 so an oversized reply is caught by the parser."""
    seen: dict[str, object] = {}

    def fake_urlopen(request: object, timeout: float) -> FakeReply:
        seen["url"], seen["timeout"] = request.full_url, timeout  # type: ignore[attr-defined]
        seen["agent"] = request.get_header("User-agent")  # type: ignore[attr-defined]
        return FakeReply(b"x" * (CFG.treasury.max_bytes + 50))

    monkeypatch.setattr(treasury.urllib.request, "urlopen", fake_urlopen)
    body = treasury.http_fetch(CFG.treasury)("https://home.treasury.gov/x")
    assert len(body) == CFG.treasury.max_bytes + 1
    assert seen == {"url": "https://home.treasury.gov/x", "timeout": CFG.treasury.timeout_seconds,
                    "agent": "LoanIQ price file"}
