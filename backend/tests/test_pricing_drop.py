"""Tests for the drop: Current minus the next month's price (app/pricing/model.py, Step 6b).

BUSINESS: the drop is the carry of holding a TBA one month longer instead of
  delivering it: one month of coupon, minus financing the price, plus principal
  prepaid at par. A desk checks that:
  - the worked example holds to the 32nd (UMBS 30 6.0 on Thanksgiving 2026: 0-03+);
  - higher financing means a smaller drop, and can make it negative;
  - faster prepayment helps a discount coupon and hurts a premium one;
  - the days come from SIFMA's calendar;
  - a negative drop reads "-0-01", and pay-ups do not change by month.
TECH: pytest on the real configs and the recorded curve (10-year 4.85, 1-month
  bill 4.27 on 2026-11-25). Every expectation is worked by hand in Decimal.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.pricing.config import PRICING_PATH, load_pricing_config
from app.pricing.format32 import to_signed_32nds
from app.pricing.model import PAR, build_price_file, cpr, drop, smm
from app.pricing.treasury import fallback_curve
from tests.pricing_fixtures import pricing_config, slotting_rules

CFG = pricing_config()
CURVE = fallback_curve(CFG.curve_tenors)
TODAY = date(2026, 11, 27)
FILE = build_price_file(CURVE, CFG, TODAY)
D = Decimal


def cell(product: str, coupon: str):  # noqa: ANN201 - a PriceCell
    """One Current cell by product name and coupon."""
    row = next(r for r in FILE.products if r.product.name == product)
    return next(c for c in row.months["Current"] if c.coupon == D(coupon))


def test_worked_example_umbs30_6() -> None:
    """BUSINESS: UMBS 30 6.0 on 2026-11-27 (curve 2026-11-25):
      price 100 - 6 x (6.20 - 6.0) = 98.80; Dec 10 -> Jan 14 = 35 days;
      financing 4.27% (1-month bill + 0 spread); gap -0.20 -> S-curve 0.352,
      CPR 6 + 19 x 0.352 = 12.688%, SMM = 1 - (1 - 0.12688)^(1/12) ~ 1.124%;
      drop = 6.0/12 - 98.80 x 0.0427 x 35/360 + 1.20 x SMM
           = 0.5000 - 0.4102 + 0.0135 = 0.1033 points = 3.3 32nds -> 0-03+."""
    m = D("0.352")
    expected_cpr = D(6) + D(19) * m
    assert cpr(D("-0.20"), CFG) == expected_cpr
    raw = drop(D("6.0"), D("98.80"), D("4.27"), 35, expected_cpr)
    by_hand = D("6.0") / 12 - D("98.80") * D("0.0427") * 35 / 360 + D("1.20") * smm(expected_cpr)
    assert raw == by_hand
    assert abs(raw - D("0.1033")) < D("0.0001")
    c = cell("UMBS 30", "6.0")
    assert c.drop == D("0.109375") and to_signed_32nds(c.drop) == "0-03+"


def test_smm_from_cpr() -> None:
    """BUSINESS: SMM = 1 - (1 - CPR)^(1/12): 0% CPR prepays nothing; 12% CPR is
    about 1.06% a month (not 1.00%: monthly prepayments compound)."""
    assert smm(D(0)) == 0
    assert abs(smm(D(12)) - D("0.010596")) < D("0.000001")
    assert ((1 - smm(D(12))) ** 12 - D("0.88")).copy_abs() < D("1e-20")


def test_cpr_follows_the_s_curve() -> None:
    """BUSINESS: 6% CPR on a deep discount, 25% on a deep premium, rising between."""
    assert cpr(D("-3"), CFG) == D(6) and cpr(D("3"), CFG) == D(25)
    speeds = [cpr(D(g) / 4, CFG) for g in range(-8, 9)]
    assert all(b >= a for a, b in zip(speeds, speeds[1:]))


def test_higher_financing_means_a_smaller_drop() -> None:
    """BUSINESS: financing is the cost of carrying the bonds; when it rises, rolling
    is worth less."""
    low = drop(D("6.0"), D("98.80"), D("3.00"), 35, D(12))
    high = drop(D("6.0"), D("98.80"), D("6.00"), 35, D(12))
    assert high < low


def test_drop_is_negative_when_financing_beats_the_coupon() -> None:
    """BUSINESS: a 2.0 coupon at 80 earns 0.167 points a month but costs
    80 x 4.27% x 35/360 = 0.332 to finance; even the slow prepayments returned at
    par do not make up the gap, so next month trades higher: a negative drop."""
    raw = drop(D("2.0"), D(80), D("4.27"), 35, D(6))
    assert raw < 0
    c = cell("UMBS 15", "2.0")
    assert c.drop < 0 and to_signed_32nds(c.drop).startswith("-")


def test_prepayment_helps_discounts_and_hurts_premiums() -> None:
    """BUSINESS: principal comes back at par: a gain on a bond bought at 90, a loss
    on one bought at 104. Faster prepayment widens a discount's drop and narrows a
    premium's."""
    assert drop(D("4.0"), D(90), D("4.27"), 35, D(25)) > drop(D("4.0"), D(90), D("4.27"), 35, D(6))
    assert drop(D("8.0"), D(104), D("4.27"), 35, D(25)) < drop(D("8.0"), D(104), D("4.27"), 35, D(6))
    assert drop(D("6.0"), PAR, D("4.27"), 35, D(25)) == drop(D("6.0"), PAR, D("4.27"), 35, D(6))


def test_more_days_more_financing() -> None:
    """BUSINESS: the days come from SIFMA: a longer gap between settlement dates
    costs more to finance. On 2026-12-09 Class A rolls Jan 14 -> Feb 11 (28 days),
    a shorter roll than December's 35, so its drop is larger."""
    later = build_price_file(CURVE, CFG, date(2026, 12, 9))
    row = next(r for r in later.products if r.product.name == "UMBS 30")
    assert row.roll.days == 28 and row.roll.current.label == "Jan 2027"
    jan = next(c for c in row.months["Current"] if c.coupon == D("6.0"))
    assert jan.drop > cell("UMBS 30", "6.0").drop


def test_financing_spread_lowers_the_drop(tmp_path: Path) -> None:
    """BUSINESS: financing_spread_pct adds to the bill yield; 50 bps more financing
    lowers every drop (prices are the same)."""
    text = PRICING_PATH.read_text(encoding="utf-8").replace(
        "financing_spread_pct = 0.0", "financing_spread_pct = 0.5")
    path = tmp_path / "pricing.toml"
    path.write_text(text, encoding="utf-8")
    wider = build_price_file(CURVE, load_pricing_config(slotting_rules(), path), TODAY)
    assert wider.products[0].financing_rate == D("4.77")
    for a, b in zip(FILE.products[0].months["Current"], wider.products[0].months["Current"]):
        assert b.price == a.price and b.drop < a.drop


def test_drops_are_on_the_half_32nd_grid() -> None:
    """BUSINESS: drops are quoted in 32nds like prices."""
    for r in FILE.products:
        for c in r.months["Current"]:
            assert (c.drop * 64) == (c.drop * 64).to_integral_value()


def test_payups_do_not_change_with_the_roll() -> None:
    """BUSINESS: pay-ups are the same in every month; only prices roll."""
    later = build_price_file(CURVE, CFG, date(2026, 12, 9))
    assert later.payups == FILE.payups


@pytest.mark.parametrize("points, text", [
    (D("0.109375"), "0-03+"), (D("-0.046875"), "-0-01+"), (D("-0.03125"), "-0-01"),
    (D("0"), "0-00"), (D("-0.001"), "0-00"),   # rounds to zero: no "-0-00"
])
def test_signed_32nds(points: Decimal, text: str) -> None:
    """BUSINESS: a negative drop shows its sign; a drop that rounds to nothing does not."""
    assert to_signed_32nds(points) == text


@pytest.mark.parametrize("old, new, reason", [
    ('financing_tenor = "1M"', 'financing_tenor = "9M"', "tenor"),
    ("cpr_ceiling_pct = 25.0", "cpr_ceiling_pct = 5.0", "cpr_ceiling_pct"),
    ("cpr_ceiling_pct = 25.0", "cpr_ceiling_pct = 100.0", "below 100"),
    ("cpr_floor_pct = 6.0", "cpr_flor_pct = 6.0", "keys"),
])
def test_bad_drop_settings_stop_the_app(tmp_path: Path, old: str, new: str, reason: str) -> None:
    """BUSINESS: a typo in the drop's settings stops the app rather than misprice
    every roll."""
    text = PRICING_PATH.read_text(encoding="utf-8")
    assert old in text
    path = tmp_path / "pricing.toml"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    with pytest.raises(ValueError, match=reason):
        load_pricing_config(slotting_rules(), path)


def test_curve_must_have_the_financing_tenor() -> None:
    """TECH: the curve cache asks for the 1-month yield as well as the anchors."""
    assert "1M" in CFG.curve_tenors and set(CFG.anchor_tenors) <= set(CFG.curve_tenors)
    assert replace(CFG, products=()).curve_tenors == ("1M",)
