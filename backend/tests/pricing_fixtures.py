"""Shared helpers for the price file tests (test_pricing_*.py).

BUSINESS: every pricing test starts from the same place: the real slotting rules
  and pricing.toml, and Treasury's curve for November 2026 as recorded into the
  repo (app/pricing/fallback_curve.xml; the last day is 2026-11-25, 10-year 4.85%).
TECH:
  - No test touches the network: FakeTreasury stands in for the HTTP fetch. It
    serves the recorded month for 202611, an empty month (the feed's real reply
    for a month with no curves yet) for any other month, or raises OSError when
    `down` is set, the way urllib does when Treasury is unreachable. It counts
    calls, so tests can check the once-a-day cache.
  - Clock is a settable clock, so tests can move the New York day forward.
"""

from __future__ import annotations

import urllib.parse
from datetime import UTC, datetime
from pathlib import Path

from app import loan_tape_gen as gen
from app.pricing.config import PRICING_PATH, PricingConfig, load_pricing_config
from app.pricing.treasury import FALLBACK_CURVE_PATH
from app.slotting import SlottingRules, load_slotting_rules
from app.spec_stories import SPEC_STORIES_PATH

RECORDED_MONTH = "202611"
RECORDED_XML = FALLBACK_CURVE_PATH.read_bytes()
# TECH: Treasury's reply for a month with no curves yet (recorded for 202612).
EMPTY_MONTH_XML = b"""<?xml version="1.0" encoding="utf-8" standalone="yes" ?>
<feed xml:base="https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml" xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices" xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata" xmlns="http://www.w3.org/2005/Atom">
<title type="text">DailyTreasuryYieldCurveRateData</title>
<id>https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml-item?data=daily_treasury_yield_curve</id>
  <updated>2026-11-27T01:04:00Z</updated>
  <link rel="self" title="DailyTreasuryYieldCurveRateData" href="DailyTreasuryYieldCurveRateData"/>
</feed>"""


def slotting_rules(stories_path: Path = SPEC_STORIES_PATH) -> SlottingRules:
    """The real slotting rules (optionally with another spec_stories.toml)."""
    cfg = gen.load_config()
    return load_slotting_rules(list(gen.COLUMNS), list(cfg["programs"]), list(cfg["products"]),
                               stories_path=stories_path)


def pricing_config(path: Path = PRICING_PATH) -> PricingConfig:
    """The real pricing.toml (or a changed copy), checked against the real rules."""
    return load_pricing_config(slotting_rules(), path)


class FakeTreasury:
    """Stands in for the HTTPS fetch. TECH: url -> XML bytes; see module docstring."""

    def __init__(self, months: dict[str, bytes] | None = None) -> None:
        self.months = {RECORDED_MONTH: RECORDED_XML} if months is None else months
        self.down = False
        self.urls: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.urls.append(url)
        if self.down:
            raise OSError("Treasury unreachable (test)")
        month = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["field_tdr_date_value_month"][0]
        return self.months.get(month, EMPTY_MONTH_XML)


class Clock:
    """A clock tests can set. TECH: returns an aware UTC datetime, like datetime.now(UTC)."""

    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def utc(*args: int) -> datetime:
    """datetime(..., tzinfo=UTC), shorter."""
    return datetime(*args, tzinfo=UTC)
