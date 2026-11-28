"""Prices in points <-> the desk's 32nds notation ("101-23+").

Where it sits:
    model.py (Decimal points) -> [to_32nds] -> API text -> the price grid (Step 6b)

BUSINESS: TBA prices are quoted in points and 32nds of a point. "101-23" means
  101 + 23/32 = 101.71875; a trailing "+" adds half a 32nd (1/64), so "101-23+"
  means 101 + 23.5/32 = 101.734375. The 32nds part is always two digits ("99-04").
  Pay-ups are quoted the same way: "0-24" is 24/32 of a point.
TECH: exact Decimal arithmetic. A price is first rounded to the nearest 1/64
  (half-even, so ties do not drift one way), then split into whole points, whole
  32nds and an optional half. Negative prices do not exist in TBA quoting and are
  refused. A drop (Step 6b) can be negative, so it has its own signed form,
  to_signed_32nds ("-0-01+").
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_EVEN, Decimal
from functools import lru_cache

SIXTY_FOURTHS = Decimal(64)
ONE = Decimal(1)
PATTERN = re.compile(r"^(\d+)-(\d{2})(\+?)$")


def round_to(value: Decimal, increment: Decimal) -> Decimal:
    """Round to the nearest multiple of increment (points), half-even.

    BUSINESS: 101.7300 to the nearest 1/64 -> 101.734375 (101-23+); a pay-up of
      22.4 32nds to the nearest half 32nd -> 22.5.
    TECH: the result keeps exactly the increment's decimal places (1/64 = 0.015625
      has six, 0.5 has one), so JSON shows "64.0", not "64.000000".
    """
    steps = (value / increment).quantize(ONE, rounding=ROUND_HALF_EVEN)
    return (steps * increment).quantize(places(increment))


@lru_cache(maxsize=64)
def places(increment: Decimal) -> Decimal:
    """The decimal places an increment has, as a quantize target: 0.015625 -> 0.000001.

    TECH: worked out once per increment (functools.lru_cache) because round_to runs
      for every price, drop and pay-up cell, about 2,000 times per price file.
    """
    return ONE.scaleb(increment.as_tuple().exponent)


def to_32nds(points: Decimal) -> str:
    """Points -> "101-23+" text. TECH: rounds to 1/64 first; refuses negatives."""
    if points < 0:
        raise ValueError(f"A price cannot be negative: {points}")
    sixty_fourths = int((points * SIXTY_FOURTHS).quantize(Decimal(1), rounding=ROUND_HALF_EVEN))
    whole, rest = divmod(sixty_fourths, 64)
    thirty_seconds, half = divmod(rest, 2)
    return f"{whole}-{thirty_seconds:02d}{'+' if half else ''}"


def from_32nds(text: str) -> Decimal:
    """"101-23+" -> Decimal("101.734375"). TECH: the 32nds must be 00 to 31."""
    match = PATTERN.match(text.strip())
    if not match or int(match.group(2)) > 31:
        raise ValueError(f"Not a price in 32nds: {text!r}")
    whole, ticks, plus = match.groups()
    return Decimal(whole) + (Decimal(ticks) + (Decimal("0.5") if plus else 0)) / 32


def to_signed_32nds(points: Decimal) -> str:
    """A signed amount, such as a drop: 0.109375 -> "0-03+", -0.046875 -> "-0-01+".

    BUSINESS: a negative drop means the next month trades ABOVE Current, which
      happens on low coupons when financing costs more than the coupon earns.
    TECH: the sign is decided after rounding, so a tiny negative that rounds to
      zero shows as "0-00", never "-0-00".
    """
    text = to_32nds(abs(points))
    return f"-{text}" if points < 0 and text != "0-00" else text
