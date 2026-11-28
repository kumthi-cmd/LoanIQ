"""Tests for the price model, 32nds notation and pricing.toml (app/pricing/).

BUSINESS: what a desk relies on in a price file, illustrative or not:
  - a coupon trades at par (100) exactly at the current coupon;
  - higher coupons are worth more, and above par the price flattens (the
    prepayment cap) rather than climbing for ever;
  - spec pay-ups are zero on discount coupons and full on premium coupons;
  - prices read correctly in 32nds ("101-23+");
  - coupons far from the market are flagged model_only;
  - a bad setting stops the app instead of pricing the wrong row.
TECH: pytest. The real configs and the recorded Treasury curve (2026-11-25) come
  from tests/pricing_fixtures.py. Config errors are tested on changed copies of
  pricing.toml written to a temp folder.
"""

from __future__ import annotations

import time
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.pricing.config import PRICING_PATH, coupon_ladder, load_pricing_config
from app.pricing.format32 import from_32nds, round_to, to_32nds
from app.pricing.model import build_price_file, current_coupon, payup_multiplier, tba_price
from app.pricing.treasury import fallback_curve
from app.spec_stories import SPEC_STORIES_PATH
from tests.pricing_fixtures import pricing_config, slotting_rules

CFG = pricing_config()
CURVE = fallback_curve(CFG.curve_tenors)
# BUSINESS: priced on Thanksgiving 2026 (the curve is Wednesday's): Current is
#   December 2026 for every SIFMA class.
TODAY = date(2026, 11, 27)
FILE = build_price_file(CURVE, CFG, TODAY)
D = Decimal


def product(name: str):  # noqa: ANN201 - a ProductConfig
    """One product's config by name."""
    return next(p for p in CFG.products if p.name == name)


def row(name: str):  # noqa: ANN201 - a ProductPrices
    """One product's priced row by name."""
    return next(r for r in FILE.products if r.product.name == name)


# -----------------------------------------------------------------------------
# 32nds notation
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("points, text", [
    (D("101.71875"), "101-23"),     # 101 + 23/32
    (D("101.734375"), "101-23+"),   # 101 + 23.5/32: "+" is half a 32nd
    (D("99"), "99-00"),             # whole points still show two digits of 32nds
    (D("100.03125"), "100-01"),
    (D("0.75"), "0-24"),            # a 24/32 pay-up
    (D("0.015625"), "0-00+"),       # the smallest tick
    (D("99.984375"), "99-31+"),     # the largest 32nds before the next point
])
def test_32nds_both_ways(points: Decimal, text: str) -> None:
    """BUSINESS: a trader reads "101-23+" as 101.734375; the screen must agree."""
    assert to_32nds(points) == text
    assert from_32nds(text) == points


def test_32nds_rounds_to_the_nearest_half_32nd() -> None:
    """BUSINESS: an unrounded model price shows on the nearest tick.
    TECH: half-even on an exact tie (1/128) so ties do not all drift up."""
    assert to_32nds(D("101.73")) == "101-23+"
    assert to_32nds(D("100.0078125")) == "100-00"   # tie between 100-00 and 100-00+


@pytest.mark.parametrize("bad", ["101-32", "101", "101-2", "-1-00", "abc"])
def test_bad_32nds_text_is_refused(bad: str) -> None:
    """TECH: 32nds run 00 to 31, always two digits."""
    with pytest.raises(ValueError):
        from_32nds(bad)


def test_negative_price_is_refused() -> None:
    """BUSINESS: no TBA trades below zero; a negative is a bug upstream."""
    with pytest.raises(ValueError):
        to_32nds(D("-0.5"))


def test_round_to_keeps_the_increments_decimals() -> None:
    """TECH: JSON shows "64.0" and "101.734375", not trailing zeros."""
    assert str(round_to(D("63.9"), D("0.5"))) == "64.0"
    assert str(round_to(D("101.73"), D("0.015625"))) == "101.734375"


# -----------------------------------------------------------------------------
# The coupon ladder and the current coupon
# -----------------------------------------------------------------------------

def test_ladder_is_25_coupons_on_slottings_step() -> None:
    """BUSINESS: 1.0 to 13.0 in slotting.toml's 0.5 step, so every slot has a price."""
    assert CFG.coupons[0] == D("1.0") and CFG.coupons[-1] == D("13.0")
    assert len(CFG.coupons) == 25
    assert all(b - a == slotting_rules().step for a, b in zip(CFG.coupons, CFG.coupons[1:]))


def test_ladder_must_end_on_a_step() -> None:
    """TECH: 1.0 to 12.75 in 0.5 steps would leave a gap at the top."""
    with pytest.raises(ValueError, match="whole number"):
        coupon_ladder(D("1.0"), D("12.75"), D("0.5"))


def test_current_coupon_is_treasury_plus_spread() -> None:
    """BUSINESS: UMBS 30 = 10-year 4.85 (2026-11-25) + 1.35 spread = 6.20%."""
    assert CURVE.curve_date.isoformat() == "2026-11-25"
    assert current_coupon(CURVE, product("UMBS 30")) == D("6.20")
    assert row("UMBS 15").current_coupon == CURVE.yields["5Y"] + product("UMBS 15").spread


# -----------------------------------------------------------------------------
# TBA prices
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("name", [p.name for p in CFG.products])
def test_par_at_the_current_coupon(name: str) -> None:
    """BUSINESS: the current coupon is, by definition, the coupon at par (100)."""
    p = product(name)
    cc = current_coupon(CURVE, p)
    assert tba_price(cc, cc, p) == D(100)


@pytest.mark.parametrize("name", [p.name for p in CFG.products])
def test_prices_rise_with_coupon(name: str) -> None:
    """BUSINESS: a higher coupon pays more interest, so it is never worth less.
    TECH: strictly rising before rounding; never falling after rounding (far
      premium coupons can round to the same tick once the curve is flat)."""
    p, cc = product(name), current_coupon(CURVE, product(name))
    raw = [tba_price(c, cc, p) for c in CFG.coupons]
    assert all(b > a for a, b in zip(raw, raw[1:]))
    rounded = [c.price for c in row(name).months["Current"]]
    assert all(b >= a for a, b in zip(rounded, rounded[1:]))


@pytest.mark.parametrize("name", [p.name for p in CFG.products])
def test_prices_flatten_above_par(name: str) -> None:
    """BUSINESS: the prepayment cap. Each coupon step above par adds less than the
    one before, the price stays under 100 + premium_cap, and below par each step
    is worth the full duration (D x 0.5 points)."""
    p, cc = product(name), current_coupon(CURVE, product(name))
    above = [tba_price(c, cc, p) for c in CFG.coupons if c > cc]
    steps = [b - a for a, b in zip(above, above[1:])]
    assert all(b < a for a, b in zip(steps, steps[1:]))
    assert max(above) < 100 + p.premium_cap
    below = [tba_price(c, cc, p) for c in CFG.coupons if c <= cc]
    assert {b - a for a, b in zip(below, below[1:])} == {p.duration * D("0.5")}


def test_no_kink_at_par() -> None:
    """BUSINESS: the premium side leaves par at the discount side's slope, so the
    coupons either side of par differ by about the same amount.
    TECH: slope just above cc within 0.1% of D."""
    p = product("UMBS 30")
    cc = current_coupon(CURVE, p)
    h = D("0.0001")
    slope = (tba_price(cc + h, cc, p) - D(100)) / h
    assert abs(slope - p.duration) < p.duration * D("0.001")


def test_deep_discount_floor() -> None:
    """BUSINESS: the straight line is held at floor_price_pts on coupons no one
    trades; a very high curve would otherwise give silly prices."""
    p = product("UMBS 30")
    high = replace(CURVE, yields={**CURVE.yields, "10Y": D("15.00")})
    cells = build_price_file(high, CFG, TODAY).products[0].months["Current"]
    assert cells[0].price == CFG.floor_price
    assert tba_price(D("1.0"), current_coupon(high, p), p) < CFG.floor_price


def test_model_only_outside_the_traded_band() -> None:
    """BUSINESS: UMBS 30 at cc 6.20 trades 2.20 to 8.20 (cc - 4.0 to cc + 2.0), so
    2.5 to 8.0 are traded and 1.0-2.0 and 8.5-13.0 are model_only."""
    cells = row("UMBS 30").months["Current"]
    traded = [c.coupon for c in cells if not c.model_only]
    assert traded[0] == D("2.5") and traded[-1] == D("8.0")
    assert all(c.model_only for c in cells if c.coupon < D("2.5") or c.coupon > D("8.0"))


def test_prices_are_on_the_half_32nd_grid() -> None:
    """BUSINESS: every price is quotable in 32nds with an optional "+"."""
    for r in FILE.products:
        for c in r.months["Current"]:
            assert (c.price * 64) == (c.price * 64).to_integral_value()
            assert from_32nds(to_32nds(c.price)) == c.price


def test_one_current_month_column() -> None:
    """BUSINESS: 6a shows one "Current" month; 6b adds the settlement calendar."""
    assert FILE.months == ("Current",)
    assert all(list(r.months) == ["Current"] for r in FILE.products)


def test_six_product_rows_in_order() -> None:
    """BUSINESS: the grid's rows, as the desk reads them."""
    assert [r.product.name for r in FILE.products] == [
        "UMBS 30", "UMBS 20", "UMBS 15", "GNMA II 30", "GNMA II 20", "GNMA II 15"]


def test_same_curve_same_file() -> None:
    """BUSINESS: a price file for any date is rebuilt from that date's curve, the
    trade date and the config, so nothing needs a disk."""
    assert build_price_file(CURVE, CFG, TODAY) == FILE


def test_price_file_builds_fast() -> None:
    """TECH: the file is rebuilt on every request, so it must be cheap: well under
    50 ms for 6 products x 25 coupons with their drops, plus 72 pay-up rows (about
    20 ms measured in Step 6b, once the drop's SMM and the rounding target were
    cached)."""
    start = time.perf_counter()
    for _ in range(5):
        build_price_file(CURVE, CFG, TODAY)
    assert (time.perf_counter() - start) / 5 < 0.05


# -----------------------------------------------------------------------------
# Spec pay-ups
# -----------------------------------------------------------------------------

def test_s_curve_ends_and_middle() -> None:
    """BUSINESS: 0 on discount coupons, 1 on premium coupons, half way at the
    middle of the ramp (gap 0 on the default -1.0 to +1.0 ramp)."""
    start, full = CFG.payup_start, CFG.payup_full
    assert payup_multiplier(D("-3"), start, full) == 0
    assert payup_multiplier(start, start, full) == 0
    assert payup_multiplier(D("0"), start, full) == D("0.5")
    assert payup_multiplier(full, start, full) == 1
    assert payup_multiplier(D("5"), start, full) == 1


def test_s_curve_rises_smoothly() -> None:
    """BUSINESS: a higher coupon never has a smaller pay-up."""
    gaps = [D(i) / 10 for i in range(-15, 16)]
    m = [payup_multiplier(g, CFG.payup_start, CFG.payup_full) for g in gaps]
    assert all(b >= a for a, b in zip(m, m[1:]))


def test_payup_zero_at_a_discount_coupon() -> None:
    """BUSINESS: on UMBS 30 at cc 6.20, the 4.0 coupon is 2.2 below the market:
    no one can refinance, so even the best story (LLB 85K) pays nothing."""
    payups = next(p for p in FILE.payups if p.product == "UMBS 30" and p.story == "LLB_85K")
    assert payups.payups_32nds[CFG.coupons.index(D("4.0"))] == 0


def test_payup_full_at_a_premium_coupon() -> None:
    """BUSINESS: at 7.5 (1.3 above cc) LLB 85K pays its full 64/32 (2 points)."""
    payups = next(p for p in FILE.payups if p.product == "UMBS 30" and p.story == "LLB_85K")
    assert payups.full_32nds == 64
    assert payups.payups_32nds[CFG.coupons.index(D("7.5"))] == 64


def test_tighter_llb_tier_pays_more_at_every_coupon() -> None:
    """BUSINESS: an $85K pool prepays more slowly than a $275K pool."""
    llb = [p for p in FILE.payups if p.product == "UMBS 30" and p.family == "LLB"]
    for i in range(len(CFG.coupons)):
        values = [p.payups_32nds[i] for p in llb]
        assert values == sorted(values, reverse=True)


def test_every_story_priced_on_every_product() -> None:
    """BUSINESS: all four story families apply to 30Y, 20Y and 15Y, so each of
    the six products has every story: 12 stories x 6 products."""
    assert len(FILE.payups) == len(CFG.stories) * len(CFG.products) == 72


def test_story_outside_a_products_term_is_not_priced(tmp_path: Path) -> None:
    """BUSINESS: a 30-year-only story gets no pay-up row on a 15-year product."""
    text = SPEC_STORIES_PATH.read_text(encoding="utf-8").replace(
        'name = "NY"\nproducts = ["30Y Fixed", "15Y Fixed", "20Y Fixed"]',
        'name = "NY"\nproducts = ["30Y Fixed"]')
    path = tmp_path / "spec_stories.toml"
    path.write_text(text, encoding="utf-8")
    cfg = load_pricing_config(slotting_rules(path))
    ny = {p.product for p in build_price_file(CURVE, cfg, TODAY).payups if p.story == "NY"}
    assert ny == {"UMBS 30", "GNMA II 30"}


# -----------------------------------------------------------------------------
# pricing.toml checks
# -----------------------------------------------------------------------------

def changed_config(tmp_path: Path, old: str, new: str) -> Path:
    """A copy of pricing.toml with one piece of text replaced."""
    text = PRICING_PATH.read_text(encoding="utf-8")
    assert old in text, old
    path = tmp_path / "pricing.toml"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return path


@pytest.mark.parametrize("old, new, reason", [
    ('agency = "UMBS"', 'agency = "FHLMC"', "agency"),
    ('term = "30Y"', 'term = "35Y"', "term"),
    ('anchor_tenor = "10Y"', 'anchor_tenor = "9Y"', "tenor"),
    ("spread_pct = 1.35", "spred_pct = 1.35", "keys"),
    ('active = "model"', 'active = "dealer"', "active"),
    ("duration_pts_per_pct = 6.0", "duration_pts_per_pct = 0", "above 0"),
    ("spread_pct = 1.35", "spread_pct = true", "number"),
    ("full_gap_pct = 1.0", "full_gap_pct = -2.0", "full_gap_pct"),
    ("coupon_max_pct = 13.0", "coupon_max_pct = 12.75", "whole number"),
    ('url = "https://', 'url = "http://', "https"),
    ('timezone = "America/New_York"', 'timezone = "Mars/Olympus"', "timezone"),
    ('months = ["Current"]', "months = []", "months"),
    ('name = "UMBS 20"', 'name = "UMBS 30"', "duplicate"),
    # TECH: anchored on its own line; "[payup_curve]" also appears in the header.
    ("\n[payup_curve]\n", "\n[payup_curv]\n", "sections"),
])
def test_bad_pricing_config_stops_the_app(tmp_path: Path, old: str, new: str, reason: str) -> None:
    """BUSINESS: a typo must stop the app, not price the wrong row or no row."""
    with pytest.raises(ValueError, match=reason):
        load_pricing_config(slotting_rules(), changed_config(tmp_path, old, new))


def test_story_without_a_payup_stops_pricing(tmp_path: Path) -> None:
    """BUSINESS: a story the desk tags but cannot price would be silently ignored
    by best execution; pricing refuses to start and names it."""
    text = SPEC_STORIES_PATH.read_text(encoding="utf-8").replace("payup_32nds = 12\n", "")
    path = tmp_path / "spec_stories.toml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="NY"):
        load_pricing_config(slotting_rules(path))


def test_stub_sources_can_be_chosen(tmp_path: Path) -> None:
    """BUSINESS: the desk-file and vendor sources are placeholders that load."""
    for name in ("file", "vendor"):
        path = changed_config(tmp_path, 'active = "model"', f'active = "{name}"')
        assert load_pricing_config(slotting_rules(), path).source == name
