"""The price file (Step 6a): illustrative TBA prices and spec pay-ups.

Where it sits:
    slotting (Step 5) -> [pricing] -> best execution (Step 6c) prices every slot

BUSINESS: what each TBA coupon is worth today and what each spec story adds,
  built from the U.S. Treasury's free daily curve because LoanIQ has no paid feed.
  Every number is illustrative (docs/decisions.md, 2026-11-27).
TECH: a package like app/agent/:
    config.py     pricing.toml, checked at start-up
    treasury.py   the Treasury XML feed: fetch, parse, one cache per New York day
    model.py      the price model, a pure function (curve, config) -> price file
    format32.py   points <-> 32nds text ("101-23+")
    sources.py    the PriceSource strategy: model now, file and vendor as stubs
    api.py        GET /api/prices/grid
"""
