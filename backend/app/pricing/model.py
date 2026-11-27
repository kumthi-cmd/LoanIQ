"""The price model: one day's Treasury curve plus the config -> the price file.

Where it sits:
    treasury.py (Curve) + config.py (PricingConfig) -> [build_price_file]
    -> PriceFile -> sources.py -> GET /api/prices/grid

BUSINESS: an illustrative stand-in for a dealer's price file, built from public
  data only (docs/decisions.md, 2026-11-27). For each product (UMBS 30, GNMA II
  15, ...):
    current coupon (percent) = Treasury par yield at the anchor tenor + spread.
      The current coupon is the coupon that would trade at par (100) today.
    TBA price (points) at each coupon, from its gap to the current coupon:
      below: 100 - D x (current coupon - coupon)          a straight line
      above: 100 + cap x (1 - e^(-D x gap / cap))         flattens toward 100 + cap
      D = duration (points per 1.00 percent of coupon), cap = premium cap (points).
      Above par the price cannot climb forever, because borrowers refinance
      high-coupon loans and investors get par back early: the prepayment cap.
    Spec pay-up (32nds) for each story at each coupon = its full pay-up x m(gap),
      m an S-curve from 0 at discount coupons to 1 at premium coupons.
  Coupons outside the product's traded band are flagged model_only: the model
  prices them, but no one would trade them today.
TECH:
  - A pure function: the same curve and config always give the same file, so a
    price file for any date can be rebuilt on demand and nothing is stored.
  - Decimal throughout; Decimal.exp() gives the premium-side curve to 28 digits.
    Prices and pay-ups are rounded to the config's increment (half a 32nd) only
    at the end, so rounding never feeds back into the formula.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from app.pricing.config import PricingConfig, ProductConfig
from app.pricing.format32 import round_to
from app.pricing.treasury import Curve, CurveStatus

PAR = Decimal(100)


@dataclass(frozen=True)
class PriceCell:
    """One coupon's TBA price. BUSINESS: coupon in percent, price in points."""
    coupon: Decimal
    price: Decimal
    model_only: bool


@dataclass(frozen=True)
class ProductPrices:
    """One grid row: a product's current coupon and its price at every coupon.

    TECH: months maps each month name ("Current") to that month's cells, in
      coupon order. Step 6b adds months.
    """
    product: ProductConfig
    anchor_yield: Decimal
    current_coupon: Decimal
    months: dict[str, tuple[PriceCell, ...]]


@dataclass(frozen=True)
class PayupRow:
    """One story's pay-up on one product, at every coupon (32nds).

    BUSINESS: LLB_85K on UMBS 30: 0 at 4.0, about 32 at 6.0, 64 at 7.5 and above.
    """
    product: str
    story: str
    family: str
    full_32nds: Decimal
    payups_32nds: tuple[Decimal, ...]


@dataclass(frozen=True)
class PriceFile:
    """The whole price file for one curve date.

    TECH: curve_status and fetched_at say how fresh the curve is (treasury.py).
    """
    as_of: date
    curve_status: CurveStatus
    fetched_at: datetime | None
    source: str
    months: tuple[str, ...]
    coupons: tuple[Decimal, ...]
    products: tuple[ProductPrices, ...]
    payups: tuple[PayupRow, ...]


def current_coupon(curve: Curve, product: ProductConfig) -> Decimal:
    """Treasury yield at the anchor tenor + spread, in percent.

    BUSINESS: 10-year at 4.85 + UMBS 30's 1.35 spread = 6.20% current coupon.
    """
    return curve.yields[product.anchor_tenor] + product.spread


def tba_price(coupon: Decimal, cc: Decimal, product: ProductConfig) -> Decimal:
    """Unrounded TBA price in points for one coupon, given the current coupon cc.

    BUSINESS: exactly 100 at cc; D points lower per 1.00 percent of coupon below
      cc; above cc it rises with the same slope at first, then flattens toward
      100 + premium_cap (see module docstring).
    TECH: both halves meet at 100 with slope D, so the curve has no kink at par.
    """
    gap = coupon - cc
    if gap <= 0:
        return PAR + product.duration * gap
    cap = product.premium_cap
    return PAR + cap * (1 - (-product.duration * gap / cap).exp())


def payup_multiplier(gap: Decimal, start: Decimal, full: Decimal) -> Decimal:
    """The S-curve m(gap): 0 up to start, 1 from full, smoothstep in between.

    BUSINESS: a spec story is worth nothing on a discount coupon (no one can
      refinance, so slow prepayment does not matter) and its full pay-up on a
      premium coupon. gap = coupon - current coupon, percent.
    TECH: smoothstep 3t^2 - 2t^3 is flat at both ends, so the pay-up does not jump
      from one coupon to the next. Exactly 0 and 1 outside the ramp (a logistic
      curve would never reach 0).
    """
    if gap <= start:
        return Decimal(0)
    if gap >= full:
        return Decimal(1)
    t = (gap - start) / (full - start)
    return t * t * (3 - 2 * t)


def price_row(curve: Curve, product: ProductConfig, cfg: PricingConfig) -> ProductPrices:
    """One product's prices at every coupon, rounded, with model_only flags.

    BUSINESS: traded band = cc - traded_below to cc + traded_above (percent).
      Prices below floor_price are raised to it (deep-discount coupons only).
    """
    cc = current_coupon(curve, product)
    low, high = cc - product.traded_below, cc + product.traded_above
    cells = tuple(
        PriceCell(c, round_to(max(tba_price(c, cc, product), cfg.floor_price), cfg.increment),
                  not low <= c <= high)
        for c in cfg.coupons)
    # TECH: 6a has one month column; every month shares the same cells until 6b
    #   adds the settlement calendar's drop between months.
    return ProductPrices(product, curve.yields[product.anchor_tenor], cc,
                         {m: cells for m in cfg.months})


def payup_rows(row: ProductPrices, cfg: PricingConfig) -> list[PayupRow]:
    """Every story's pay-up on one product, at every coupon.

    BUSINESS: only stories that apply to the product's term (a story listed
      for 30Y Fixed only would not price on UMBS 15).
    TECH: pay-ups in 32nds, rounded to the config's increment in 32nds.
    """
    # TECH: the increment in 32nds (1/64 point -> 0.5). normalize() drops the
    #   trailing zeros the multiplication leaves (0.500000 -> 0.5).
    tick = (cfg.increment * 32).normalize()
    out = []
    for story in cfg.stories:
        if row.product.term not in cfg.story_terms[story.name]:
            continue
        full = story.payup_32nds or Decimal(0)
        values = tuple(round_to(full * payup_multiplier(c - row.current_coupon, cfg.payup_start,
                                                        cfg.payup_full), tick)
                       for c in cfg.coupons)
        out.append(PayupRow(row.product.name, story.name, story.family, full, values))
    return out


def build_price_file(curve: Curve, cfg: PricingConfig, status: CurveStatus = "live",
                     fetched_at: datetime | None = None, source: str = "model") -> PriceFile:
    """The price file for one curve: every product's prices and pay-ups.

    BUSINESS: the same curve and config always give the same file.
    TECH: about 1,950 Decimal formulas on the default config (6 products x 25
      coupons, plus pay-ups); a timing test keeps it well under a second.
    """
    rows = tuple(price_row(curve, p, cfg) for p in cfg.products)
    payups = tuple(r for row in rows for r in payup_rows(row, cfg))
    return PriceFile(curve.curve_date, status, fetched_at, source, cfg.months, cfg.coupons,
                     rows, payups)
