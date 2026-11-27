"""The PriceSource strategy: where the price file comes from.

Where it sits:
    GET /api/prices/grid -> [PriceSource.price_file] -> model | file | vendor

BUSINESS: a real desk prices from a dealer's or vendor's price file, or from its
  own. LoanIQ builds an illustrative one from the Treasury curve (the model), and
  keeps a place for the other two so swapping the source is a config change
  (pricing.toml [source] active), the same way Ask the Tape swaps AI vendors.
TECH:
  - Strategy pattern, like app/agent/providers/base.py: PriceSource is an
    abstract base class (ABC) with one method, price_file(). Callers never know
    which source they hold.
  - ModelPriceSource works today. FilePriceSource and VendorPriceSource are stubs:
    they raise PriceSourceNotConfigured, which the API turns into HTTP 503.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import UTC, datetime

from app.pricing.config import PricingConfig
from app.pricing.model import PriceFile, build_price_file
from app.pricing.treasury import CurveCache, Fetch


class PriceSourceNotConfigured(RuntimeError):
    """The chosen price source is not built yet, or has nothing to read."""


class PriceSource(ABC):
    """Anything that can hand over today's price file.

    BUSINESS: best execution (Step 6c) asks this for prices and does not care
      whether they came from the model, a file or a vendor.
    TECH: `name` is the pricing.toml [source] value; it is reported in the API.
    """
    name: str

    @abstractmethod
    def price_file(self) -> PriceFile:
        """Today's price file. Raises PriceSourceNotConfigured if unavailable."""


class ModelPriceSource(PriceSource):
    """Illustrative prices from the Treasury curve and pricing.toml.

    TECH: the curve comes from CurveCache (one fetch per New York day); the file is
      rebuilt on each call, which takes a few milliseconds, so there is no second
      cache to go stale.
    """
    name = "model"

    def __init__(self, cfg: PricingConfig, curves: CurveCache) -> None:
        self.cfg = cfg
        self.curves = curves

    def price_file(self) -> PriceFile:
        """Today's curve -> the price file, with the curve's freshness attached."""
        result = self.curves.get()
        return build_price_file(result.curve, self.cfg, result.status, result.fetched_at, self.name)


class FilePriceSource(PriceSource):
    """STUB: a desk's own price file (for example a CSV of coupon and price).

    BUSINESS: lets a desk price from the marks it trusts. Not built yet.
    """
    name = "file"

    def price_file(self) -> PriceFile:
        """TECH: always raises until a later step defines the file's format."""
        raise PriceSourceNotConfigured("The desk price file source is not configured (not built yet)")


class VendorPriceSource(PriceSource):
    """STUB: a commercial data vendor's TBA and pay-up feed.

    BUSINESS: production desks buy this; LoanIQ has no paid feed. Not built.
    """
    name = "vendor"

    def price_file(self) -> PriceFile:
        """TECH: always raises; an adapter would translate the vendor's format."""
        raise PriceSourceNotConfigured("The vendor price feed is not configured (LoanIQ has no paid feed)")


def build_price_source(cfg: PricingConfig, fetch: Fetch | None = None,
                       clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> PriceSource:
    """The source pricing.toml names. TECH: fetch and clock are for tests."""
    if cfg.source == "file":
        return FilePriceSource()
    if cfg.source == "vendor":
        return VendorPriceSource()
    return ModelPriceSource(cfg, CurveCache(cfg.treasury, cfg.anchor_tenors, fetch, clock))
