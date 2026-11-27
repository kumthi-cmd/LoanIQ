"""Load and check pricing.toml, together with the slotting rules it builds on.

Where it sits:
    config/pricing.toml + slotting rules (Step 5a) -> [load_pricing_config]
    -> PricingConfig -> model.py, treasury.py, sources.py

BUSINESS: one checked set of pricing settings. A product that slotting does not
  know (a typo like "UMBS" "35Y"), a Treasury tenor the feed does not publish, or a
  spec story with no pay-up stops the app at start-up, instead of quietly pricing
  nothing or pricing the wrong row.
TECH:
  - tomllib (Python's built-in TOML reader) gives plain dicts and floats. Every
    number becomes Decimal(str(x)), so 1.35 stays exactly 1.35 (a float would be
    1.3500000000000000888...). The model then works in exact Decimal arithmetic.
  - The coupon step comes from SlottingRules.step (slotting.toml
    coupon_step_pct), so slots and prices can never disagree on the ladder.
  - Frozen dataclasses: settings cannot change after the check.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.pricing.treasury import TENOR_FIELDS
from app.slotting import SlottingRules
from app.spec_stories import Story

PRICING_PATH = Path(__file__).resolve().parent.parent / "config" / "pricing.toml"
SOURCES = ("model", "file", "vendor")

TOP_KEYS = {"source", "treasury", "grid", "payup_curve", "product"}
TREASURY_KEYS = {"url", "data", "timezone", "timeout_seconds", "max_bytes", "retry_minutes"}
GRID_KEYS = {"months", "coupon_min_pct", "coupon_max_pct", "price_increment_32nds",
             "floor_price_pts"}
CURVE_KEYS = {"start_gap_pct", "full_gap_pct"}
PRODUCT_KEYS = {"name", "agency", "term", "anchor_tenor", "spread_pct",
                "duration_pts_per_pct", "premium_cap_pts", "traded_below_pct",
                "traded_above_pct"}


@dataclass(frozen=True)
class TreasuryConfig:
    """Where and how to fetch the daily curve.

    BUSINESS: the New York day decides when a new curve is due.
    TECH: timeout in seconds, max_bytes caps the reply, retry_minutes spaces out
      attempts during an outage. tz is a zoneinfo time zone ("America/New_York").
    """
    url: str
    data: str
    tz: ZoneInfo
    timeout_seconds: float
    max_bytes: int
    retry_minutes: int


@dataclass(frozen=True)
class ProductConfig:
    """One price-grid row, such as UMBS 30.

    BUSINESS: current coupon = Treasury yield at anchor_tenor + spread (percent);
      duration is points of price per 1.00 percent of coupon below the current
      coupon; premium_cap is how far above par (points) the price can climb;
      traded_below / traded_above set the band of actively traded coupons
      (percent either side of the current coupon). All illustrative.
    """
    name: str
    agency: str
    term: str
    anchor_tenor: str
    spread: Decimal
    duration: Decimal
    premium_cap: Decimal
    traded_below: Decimal
    traded_above: Decimal


@dataclass(frozen=True)
class PricingConfig:
    """Every pricing setting, checked, plus the stories to price pay-ups for.

    BUSINESS: coupons is the 25-coupon ladder (percent); increment is the price
      tick in points (half a 32nd = 1/64 point); payup start/full are the S-curve's
      ends in coupon-minus-current-coupon (percent).
    TECH: stories are spec_stories.toml's, tiers expanded, each with a pay-up.
      story_terms maps each story to the terms it applies to ("LLB_85K" ->
      {"30Y", "20Y", "15Y"}), read from its products through slotting's terms.
    """
    source: str
    treasury: TreasuryConfig
    months: tuple[str, ...]
    coupons: tuple[Decimal, ...]
    increment: Decimal
    floor_price: Decimal
    payup_start: Decimal
    payup_full: Decimal
    products: tuple[ProductConfig, ...]
    stories: tuple[Story, ...]
    story_terms: dict[str, frozenset[str]]

    @property
    def anchor_tenors(self) -> tuple[str, ...]:
        """BUSINESS: the Treasury tenors the products need (10Y, 7Y, 5Y)."""
        return tuple(dict.fromkeys(p.anchor_tenor for p in self.products))


def number(section: str, raw: dict[str, Any], key: str, positive: bool = True) -> Decimal:
    """One number from the config as an exact Decimal.

    TECH: refuses bool (TOML `true` would count as 1) and text. positive=True
      requires > 0; otherwise >= 0 is enough.
    """
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Pricing {section}: {key} must be a number")
    out = Decimal(str(value))
    if out < 0 or (positive and out == 0):
        raise ValueError(f"Pricing {section}: {key} must be {'above' if positive else 'at least'} 0")
    return out


def exact_keys(section: str, raw: Any, keys: set[str]) -> dict[str, Any]:
    """A table with exactly the expected keys. TECH: catches typos like spred_pct."""
    if not isinstance(raw, dict) or set(raw) != keys:
        got = sorted(raw) if isinstance(raw, dict) else raw
        raise ValueError(f"Pricing {section}: keys must be exactly {sorted(keys)}, got {got}")
    return raw


def load_treasury(raw: Any) -> TreasuryConfig:
    """[treasury] -> TreasuryConfig. TECH: the time zone must exist (tzdata)."""
    t = exact_keys("treasury", raw, TREASURY_KEYS)
    if not str(t["url"]).startswith("https://"):
        raise ValueError("Pricing treasury: url must be https")
    try:
        tz = ZoneInfo(t["timezone"])
    except (ZoneInfoNotFoundError, ValueError) as err:
        raise ValueError(f"Pricing treasury: unknown timezone {t['timezone']!r}") from err
    return TreasuryConfig(t["url"], t["data"], tz, float(number("treasury", t, "timeout_seconds")),
                          int(number("treasury", t, "max_bytes")),
                          int(number("treasury", t, "retry_minutes")))


def coupon_ladder(low: Decimal, high: Decimal, step: Decimal) -> tuple[Decimal, ...]:
    """Every coupon from low to high in steps, percent: 1.0, 1.5, ..., 13.0.

    BUSINESS: the coupons a TBA can be quoted at. TECH: low and high must sit on
      the step, so the ladder ends exactly on high.
    """
    if high <= low or (high - low) % step != 0:
        raise ValueError(f"Pricing grid: {low} to {high} must be a whole number of {step} steps")
    count = int((high - low) / step) + 1
    return tuple(low + step * i for i in range(count))


def load_product(raw: Any, rules: SlottingRules) -> ProductConfig:
    """One [[product]] table, checked against slotting's agencies and terms.

    BUSINESS: every price row must match a slot a loan can land in.
    """
    p = exact_keys(f"product {raw.get('name', '?') if isinstance(raw, dict) else '?'}",
                   raw, PRODUCT_KEYS)
    where = f"product {p['name']}"
    if p["agency"] not in rules.agency_names:
        raise ValueError(f"Pricing {where}: agency {p['agency']!r} is not in slotting.toml")
    if p["term"] not in set(rules.terms.values()):
        raise ValueError(f"Pricing {where}: term {p['term']!r} is not in slotting.toml")
    if p["anchor_tenor"] not in TENOR_FIELDS:
        raise ValueError(f"Pricing {where}: unknown Treasury tenor {p['anchor_tenor']!r}")
    return ProductConfig(p["name"], p["agency"], p["term"], p["anchor_tenor"],
                         number(where, p, "spread_pct", positive=False),
                         number(where, p, "duration_pts_per_pct"),
                         number(where, p, "premium_cap_pts"),
                         number(where, p, "traded_below_pct", positive=False),
                         number(where, p, "traded_above_pct", positive=False))


def priced_stories(stories: tuple[Story, ...]) -> tuple[Story, ...]:
    """Every spec story, refusing one without a pay-up.

    BUSINESS: a story the desk tags loans with but cannot price would make best
      execution quietly ignore it; better to stop and say which one.
    """
    missing = [s.name for s in stories if s.payup_32nds is None]
    if missing:
        raise ValueError(f"Pricing: spec stories without payup_32nds in spec_stories.toml: {missing}")
    return stories


def load_pricing_config(rules: SlottingRules, path: Path = PRICING_PATH) -> PricingConfig:
    """Load and check pricing.toml against the slotting rules. The one entry point.

    BUSINESS: if any setting is wrong the app does not start.
    TECH: rules are the validated slotting rules (agencies, terms, coupon step and
      the spec stories). Raises ValueError naming the bad setting.
    """
    with path.open("rb") as f:
        raw = tomllib.load(f)
    if set(raw) != TOP_KEYS:
        raise ValueError(f"Pricing: sections must be exactly {sorted(TOP_KEYS)}, got {sorted(raw)}")
    source = exact_keys("source", raw["source"], {"active"})["active"]
    if source not in SOURCES:
        raise ValueError(f"Pricing source: active must be one of {list(SOURCES)}, got {source!r}")
    grid = exact_keys("grid", raw["grid"], GRID_KEYS)
    curve = exact_keys("payup_curve", raw["payup_curve"], CURVE_KEYS)
    start, full = Decimal(str(curve["start_gap_pct"])), Decimal(str(curve["full_gap_pct"]))
    if full <= start:
        raise ValueError("Pricing payup_curve: full_gap_pct must be above start_gap_pct")
    months = grid["months"]
    if not isinstance(months, list) or not months or len(set(months)) != len(months):
        raise ValueError("Pricing grid: months must be a list of distinct names")
    products = tuple(load_product(p, rules) for p in raw["product"])
    names = [p.name for p in products]
    if len(set(names)) != len(names):
        raise ValueError(f"Pricing: duplicate product names {names}")
    return PricingConfig(
        source, load_treasury(raw["treasury"]), tuple(months),
        coupon_ladder(number("grid", grid, "coupon_min_pct"), number("grid", grid, "coupon_max_pct"),
                      rules.step),
        number("grid", grid, "price_increment_32nds") / 32,
        number("grid", grid, "floor_price_pts", positive=False),
        start, full, products, priced_stories(rules.stories),
        {s.name: frozenset(rules.terms[p] for p in s.products if p in rules.terms)
         for s in rules.stories})
