"""The price file route: GET /api/prices/grid.

Where it sits:
    price grid screen (Step 6b), best execution (Step 6c)
    -> [GET /api/prices/grid] -> PricingService -> PriceSource -> PriceFile

BUSINESS: one call gives the whole illustrative price file: the curve date and
  its label ("Illustrative, as of 2026-11-25"), every product's current coupon
  and TBA price at every coupon (in points and in 32nds, with model_only flags),
  every spec story's pay-up at every coupon, and where the numbers come from.
TECH:
  - Pydantic models describe the response; FastAPI turns them into the OpenAPI
    spec, from which the front end's TypeScript types are generated.
  - Prices and pay-ups are Decimal. Pydantic writes a Decimal to JSON as a string
    ("101.734375"), so no digit is lost to floating point on the way.
  - PricingService is built once in main.py's lifespan as app.state.prices and
    reached through a FastAPI dependency, like the slotting service.
  - Visitor-facing words come from content/pricing.json.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.pricing.format32 import to_32nds
from app.pricing.model import PayupRow, PriceFile, ProductPrices
from app.pricing.sources import PriceSource, PriceSourceNotConfigured

router = APIRouter()
WORDS_PATH = Path(__file__).resolve().parents[3] / "content" / "pricing.json"


# =============================================================================
# Response models
# =============================================================================

class PriceCellOut(BaseModel):
    """One coupon's TBA price. BUSINESS: coupon percent; price points; "101-23+"."""
    coupon: Decimal
    price: Decimal
    price_32nds: str
    model_only: bool


class MonthPrices(BaseModel):
    """One delivery month's prices for a product. TECH: 6a sends "Current" only."""
    month: str
    cells: list[PriceCellOut]


class ProductRow(BaseModel):
    """One price-grid row.

    BUSINESS: current_coupon_pct = anchor_yield_pct + spread_pct, the coupon that
      trades at par today. traded_low_pct and traded_high_pct bound the actively
      traded coupons; cells outside are model_only.
    """
    name: str
    agency: str
    term: str
    anchor_tenor: str
    anchor_yield_pct: Decimal
    spread_pct: Decimal
    current_coupon_pct: Decimal
    traded_low_pct: Decimal
    traded_high_pct: Decimal
    months: list[MonthPrices]


class PayupCell(BaseModel):
    """One story's pay-up at one coupon. BUSINESS: in 32nds, and as "0-24+"."""
    coupon: Decimal
    payup_32nds: Decimal
    payup_text: str


class PayupRowOut(BaseModel):
    """One story on one product. BUSINESS: full_32nds is the premium-coupon pay-up."""
    product: str
    story: str
    story_label: str
    family: str
    full_32nds: Decimal
    cells: list[PayupCell]


class SourceOut(BaseModel):
    """Where a number comes from. TECH: url is None for LoanIQ's own model."""
    name: str
    url: str | None
    used_for: str


class PriceGrid(BaseModel):
    """GET /api/prices/grid.

    BUSINESS: as_of is the Treasury curve's date; label is the line every price
      screen shows; curve_status says whether the curve was fetched today (live),
      kept from an earlier fetch because Treasury was down (cached), or the
      bundled sample (fixture). illustrative is always true.
    """
    as_of: date
    label: str
    curve_status: Literal["live", "cached", "fixture"]
    curve_fetched_at: datetime | None
    price_source: str
    illustrative: bool
    months: list[str]
    coupons: list[Decimal]
    products: list[ProductRow]
    payups: list[PayupRowOut]
    sources: list[SourceOut]


# =============================================================================
# Service and conversion
# =============================================================================

def load_pricing_words(path: Path = WORDS_PATH) -> dict[str, Any]:
    """The visitor-facing words in content/pricing.json."""
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass
class PricingService:
    """The price source plus the words the response needs.

    TECH: story_labels maps story name -> display label ("LOW_FICO" -> "Low
      FICO"), from content/slotting.json via slotting.story_labels.
    """
    source: PriceSource
    words: dict[str, Any]
    story_labels: dict[str, str]

    def grid(self) -> PriceGrid:
        """Today's price file as the API response."""
        return to_grid(self.source.price_file(), self.words, self.story_labels)


def product_row(row: ProductPrices) -> ProductRow:
    """One product's prices -> its response row."""
    p = row.product
    return ProductRow(
        name=p.name, agency=p.agency, term=p.term, anchor_tenor=p.anchor_tenor,
        anchor_yield_pct=row.anchor_yield, spread_pct=p.spread,
        current_coupon_pct=row.current_coupon,
        traded_low_pct=row.current_coupon - p.traded_below,
        traded_high_pct=row.current_coupon + p.traded_above,
        months=[MonthPrices(month=m, cells=[PriceCellOut(coupon=c.coupon, price=c.price,
                                                         price_32nds=to_32nds(c.price),
                                                         model_only=c.model_only)
                                            for c in cells])
                for m, cells in row.months.items()])


def payup_row(row: PayupRow, coupons: tuple[Decimal, ...], labels: dict[str, str]) -> PayupRowOut:
    """One story's pay-ups -> its response row. BUSINESS: 24 32nds -> "0-24"."""
    return PayupRowOut(product=row.product, story=row.story,
                       story_label=labels.get(row.story, row.story), family=row.family,
                       full_32nds=row.full_32nds,
                       cells=[PayupCell(coupon=c, payup_32nds=v, payup_text=to_32nds(v / 32))
                              for c, v in zip(coupons, row.payups_32nds)])


def to_grid(pf: PriceFile, words: dict[str, Any], labels: dict[str, str]) -> PriceGrid:
    """A PriceFile -> the API response, with its label filled in."""
    return PriceGrid(
        as_of=pf.as_of, label=words["label"][pf.curve_status].format(as_of=pf.as_of.isoformat()),
        curve_status=pf.curve_status, curve_fetched_at=pf.fetched_at, price_source=pf.source,
        illustrative=True, months=list(pf.months), coupons=list(pf.coupons),
        products=[product_row(r) for r in pf.products],
        payups=[payup_row(r, pf.coupons, labels) for r in pf.payups],
        sources=[SourceOut(**s) for s in words["sources"]])


def get_pricing(request: Request) -> PricingService:
    """FastAPI dependency: the pricing service built at start-up (main.py lifespan).

    TECH: 503 when the app was built without slotting rules (hand-built test
      stores), since prices need the coupon step and the spec stories.
    """
    service = getattr(request.app.state, "prices", None)
    if service is None:
        raise HTTPException(503, "Pricing is not set up on this server")
    return service


# =============================================================================
# Routes
# =============================================================================

@router.get("/api/prices/grid", response_model=PriceGrid)
def price_grid(service: Annotated[PricingService, Depends(get_pricing)]) -> PriceGrid:
    """BUSINESS: today's illustrative price file.

    TECH: the first call of a New York day fetches Treasury's curve (up to the
      timeout); later calls reuse it. 503 if the configured source is a stub.
    """
    try:
        return service.grid()
    except PriceSourceNotConfigured as err:
        raise HTTPException(503, str(err)) from err
