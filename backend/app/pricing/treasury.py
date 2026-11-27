"""The daily anchor: the U.S. Treasury's Daily Par Yield Curve, fetched and cached.

Where it sits:
    home.treasury.gov XML feed -> [CurveCache.get] -> model.py builds the price file

BUSINESS: mortgage rates move with Treasury yields, so the price file is anchored
  to Treasury's daily par yield curve: free, public and published every business
  day after the close. LoanIQ fetches it on the first request of each New York day
  and reuses it all day. If Treasury cannot be reached it keeps the last curve it
  fetched; with none at all it uses a curve recorded into the repo
  (fallback_curve.xml, November 2026) and the label says so. Weekends and holidays
  have no curve, so "today's" curve is the latest one dated on or before today
  (on Thanksgiving, the Wednesday before).
TECH:
  - The feed is an Atom XML document, one calendar month per request. Each
    <entry> has <m:properties> with <d:NEW_DATE> (the curve date) and one
    <d:BC_10YEAR>-style element per tenor, in percent.
  - Parsed with the standard library's xml.etree.ElementTree. XML can declare
    entities that expand to gigabytes ("billion laughs"); the feed never uses a
    DOCTYPE, so any reply containing one is refused before parsing, and replies
    above max_bytes are refused too.
  - fetch is a plain function (url -> bytes) passed into CurveCache, so tests hand
    it the recorded XML and CI never touches the network. clock is passed in the
    same way, so tests can move the day forward.
  - One lock around get(): two first-requests of the day fetch once, not twice.
    A request may wait up to the timeout while another fetches; that happens at
    most once a day (or once per retry_minutes in an outage).
"""

from __future__ import annotations

import logging
import threading
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:  # TECH: import only for type hints, avoiding a circular import
    from app.pricing.config import TreasuryConfig

log = logging.getLogger(__name__)

FALLBACK_CURVE_PATH = Path(__file__).resolve().parent / "fallback_curve.xml"

# TECH: the feed's XML namespaces (Microsoft OData), and its tenor element names.
NS_D = "{http://schemas.microsoft.com/ado/2007/08/dataservices}"
NS_M = "{http://schemas.microsoft.com/ado/2007/08/dataservices/metadata}"
TENOR_FIELDS = {
    "1M": "BC_1MONTH", "2M": "BC_2MONTH", "3M": "BC_3MONTH", "4M": "BC_4MONTH",
    "6M": "BC_6MONTH", "1Y": "BC_1YEAR", "2Y": "BC_2YEAR", "3Y": "BC_3YEAR",
    "5Y": "BC_5YEAR", "7Y": "BC_7YEAR", "10Y": "BC_10YEAR", "20Y": "BC_20YEAR",
    "30Y": "BC_30YEAR",
}

# BUSINESS: live = fetched today; cached = Treasury unreachable, last curve kept;
#   fixture = never reached Treasury, recorded curve in use.
CurveStatus = Literal["live", "cached", "fixture"]
Fetch = Callable[[str], bytes]


class CurveError(ValueError):
    """The feed's reply is not a usable curve (bad XML, too big, no dates)."""


@dataclass(frozen=True)
class Curve:
    """One day's par yield curve.

    BUSINESS: yields["10Y"] = 4.85 means the 10-year Treasury par yield was 4.85%.
    TECH: Decimal percent, exactly as published (two decimals).
    """
    curve_date: date
    yields: dict[str, Decimal]


@dataclass(frozen=True)
class CurveResult:
    """The curve to price from, and how fresh it is.

    TECH: fetched_at is when it came from Treasury (UTC); None for the fixture.
    """
    curve: Curve
    status: CurveStatus
    fetched_at: datetime | None


def parse_value(text: str | None) -> Decimal | None:
    """One tenor's yield text -> Decimal percent, or None if blank or not a number."""
    if not text or not text.strip():
        return None
    try:
        return Decimal(text.strip())
    except InvalidOperation:
        return None


def parse_curve_xml(body: bytes, max_bytes: int = 2_000_000) -> list[Curve]:
    """Every curve in one month of the feed, in date order.

    BUSINESS: one curve per business day of the month.
    TECH: refuses replies over max_bytes and any DOCTYPE or ENTITY (see module
      docstring). Tenors with no value on a day (Treasury added the 2-month and
      4-month later, for example) are simply missing from that day's yields.
      Raises CurveError for anything that is not the feed's XML.
    """
    if len(body) > max_bytes:
        raise CurveError(f"Treasury reply is {len(body)} bytes, over the {max_bytes} limit")
    if b"<!DOCTYPE" in body or b"<!ENTITY" in body:
        raise CurveError("Treasury reply declares a DOCTYPE or ENTITY; refused")
    try:
        root = ET.fromstring(body)
    except ET.ParseError as err:
        raise CurveError(f"Treasury reply is not XML: {err}") from err
    curves = []
    for props in root.iter(f"{NS_M}properties"):
        raw_date = props.findtext(f"{NS_D}NEW_DATE")
        if not raw_date:
            continue
        yields = {tenor: value for tenor, field in TENOR_FIELDS.items()
                  if (value := parse_value(props.findtext(f"{NS_D}{field}"))) is not None}
        curves.append(Curve(date.fromisoformat(raw_date[:10]), yields))
    return sorted(curves, key=lambda c: c.curve_date)


def latest_on_or_before(curves: Iterable[Curve], day: date,
                        tenors: Iterable[str] = ()) -> Curve | None:
    """The newest curve dated on or before `day` that has every tenor needed.

    BUSINESS: on a weekend or holiday, the last business day's curve.
    """
    needed = set(tenors)
    usable = [c for c in curves if c.curve_date <= day and needed <= set(c.yields)]
    return max(usable, key=lambda c: c.curve_date, default=None)


def month_url(cfg: TreasuryConfig, month: date) -> str:
    """The feed's URL for one calendar month.

    TECH: urlencode escapes the values, so the query string is always well formed.
    """
    query = urllib.parse.urlencode({"data": cfg.data,
                                    "field_tdr_date_value_month": month.strftime("%Y%m")})
    return f"{cfg.url}?{query}"


def previous_month(day: date) -> date:
    """The first day of the month before `day`'s month."""
    return (day.replace(day=1) - timedelta(days=1)).replace(day=1)


def http_fetch(cfg: TreasuryConfig) -> Fetch:
    """The real fetch: HTTPS GET with a timeout, reading at most max_bytes + 1.

    TECH: urllib.request is the standard library's HTTP client, so no new
      dependency. Reading one byte past the limit lets parse_curve_xml see that
      the reply was too big. Only https URLs from the checked config reach here.
    """
    def fetch(url: str) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": "LoanIQ price file"})
        with urllib.request.urlopen(request, timeout=cfg.timeout_seconds) as reply:  # noqa: S310
            return reply.read(cfg.max_bytes + 1)
    return fetch


def fetch_curve(cfg: TreasuryConfig, fetch: Fetch, today: date, tenors: Iterable[str]) -> Curve:
    """Today's curve from the feed: this month, or last month if none yet.

    BUSINESS: on the 1st of a month (or a holiday on the 1st) this month has no
      curve yet, so the last business day of the previous month is used.
    TECH: raises CurveError if neither month has a usable curve.
    """
    tenors = tuple(tenors)
    for month in (today.replace(day=1), previous_month(today)):
        curve = latest_on_or_before(parse_curve_xml(fetch(month_url(cfg, month)), cfg.max_bytes),
                                    today, tenors)
        if curve is not None:
            return curve
    raise CurveError(f"Treasury has no curve with {list(tenors)} on or before {today}")


def fallback_curve(tenors: Iterable[str], path: Path = FALLBACK_CURVE_PATH) -> Curve:
    """The recorded curve: the latest day in the bundled month that has every tenor.

    BUSINESS: lets LoanIQ show prices even if it has never reached Treasury.
    """
    curve = latest_on_or_before(parse_curve_xml(path.read_bytes()), date.max, tenors)
    if curve is None:
        raise CurveError(f"{path.name} has no curve with {list(tenors)}")
    return curve


class CurveCache:
    """Today's curve, fetched once per New York day, with fallbacks.

    BUSINESS: the order is (1) today's fetch, (2) the last curve fetched if
      Treasury is down, (3) the recorded curve if nothing was ever fetched.
    TECH: fetch and clock are injectable for tests (clock returns an aware
      datetime). After a failed fetch, the next try waits retry_minutes.
    """

    def __init__(self, cfg: TreasuryConfig, tenors: Iterable[str], fetch: Fetch | None = None,
                 clock: Callable[[], datetime] = lambda: datetime.now(UTC),
                 fallback_path: Path = FALLBACK_CURVE_PATH) -> None:
        self.cfg = cfg
        self.tenors = tuple(tenors)
        self.fetch = fetch or http_fetch(cfg)
        self.clock = clock
        self.fallback_path = fallback_path
        self.lock = threading.Lock()
        self.last: CurveResult | None = None     # TECH: the last good fetch
        self.fetched_day: date | None = None     # New York day of that fetch
        self.failed_at: datetime | None = None   # last failed attempt, for the retry wait

    def get(self) -> CurveResult:
        """The curve to price from now. BUSINESS: see the class docstring."""
        with self.lock:
            now = self.clock()
            today = now.astimezone(self.cfg.tz).date()
            if self.last is not None and self.fetched_day == today:
                return self.last
            if self.failed_at is None or now - self.failed_at >= timedelta(minutes=self.cfg.retry_minutes):
                result = self.try_fetch(now, today)
                if result is not None:
                    return result
            return self.stale()

    def try_fetch(self, now: datetime, today: date) -> CurveResult | None:
        """One attempt at Treasury. TECH: any network or format problem -> None, logged."""
        try:
            curve = fetch_curve(self.cfg, self.fetch, today, self.tenors)
        except (OSError, urllib.error.URLError, CurveError, ValueError) as err:
            # TECH: URLError and socket timeouts are OSErrors; ValueError covers a
            #   bad date in the XML. The message goes to the log, never to a visitor.
            log.warning("treasury_fetch_failed %s", err)
            self.failed_at = now
            return None
        self.last, self.fetched_day, self.failed_at = CurveResult(curve, "live", now), today, None
        return self.last

    def stale(self) -> CurveResult:
        """Treasury is unreachable: the last curve fetched, else the recorded one."""
        if self.last is not None:
            return CurveResult(self.last.curve, "cached", self.last.fetched_at)
        return CurveResult(fallback_curve(self.tenors, self.fallback_path), "fixture", None)
