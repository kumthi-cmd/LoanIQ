"""Tests for GET /api/prices/grid and the PriceSource strategy (app/pricing/api.py, sources.py).

BUSINESS: what the price grid screen (Step 6b) and best execution (Step 6c) will
  read: the curve date and its "Illustrative, as of ..." label, six product rows
  of 25 coupons in points and 32nds with model_only flags, every story's pay-up,
  and the sources. The label must change when Treasury is down. A stub source
  answers "not configured" rather than inventing prices.
TECH: FastAPI's TestClient on a small app holding only the pricing router, with
  the service built exactly as main.py builds it (main.build_pricing), so no tape
  has to be generated. The real app's OpenAPI spec is checked for the route.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import main
from app.pricing import api as pricing_api
from app.pricing.sources import (FilePriceSource, ModelPriceSource, PriceSourceNotConfigured,
                                 VendorPriceSource, build_price_source)
from app.slotting import load_slotting_words
from tests.pricing_fixtures import Clock, FakeTreasury, pricing_config, slotting_rules, utc


def client_for(service: pricing_api.PricingService | None) -> TestClient:
    """A TestClient on an app with only the pricing route and this service."""
    app = FastAPI()
    app.include_router(pricing_api.router)
    app.state.prices = service
    return TestClient(app)


@pytest.fixture(scope="module")
def fake() -> FakeTreasury:
    """The recorded November 2026 feed, shared by the module's live service."""
    return FakeTreasury()


@pytest.fixture(scope="module")
def grid(fake: FakeTreasury) -> dict:
    """GET /api/prices/grid on the real configs and the recorded curve."""
    service = main.build_pricing(slotting_rules(), load_slotting_words(), fake)
    response = client_for(service).get("/api/prices/grid")
    assert response.status_code == 200
    return response.json()


def test_grid_is_labelled_illustrative_with_the_curve_date(grid: dict) -> None:
    """BUSINESS: every price screen says these are illustrative, and as of when."""
    assert grid["as_of"] == "2026-11-25"
    assert grid["label"] == "Illustrative, as of 2026-11-25"
    assert grid["curve_status"] == "live" and grid["illustrative"] is True
    assert grid["price_source"] == "model" and grid["curve_fetched_at"]


def test_grid_rows_coupons_and_months(grid: dict) -> None:
    """BUSINESS: six rows, one "Current" month, 25 coupons 1.0 to 13.0."""
    assert [p["name"] for p in grid["products"]] == [
        "UMBS 30", "UMBS 20", "UMBS 15", "GNMA II 30", "GNMA II 20", "GNMA II 15"]
    assert grid["months"] == ["Current"]
    assert len(grid["coupons"]) == 25 and grid["coupons"][0] == "1.0" and grid["coupons"][-1] == "13.0"
    for p in grid["products"]:
        assert [m["month"] for m in p["months"]] == ["Current"]
        assert len(p["months"][0]["cells"]) == 25


def test_umbs30_row(grid: dict) -> None:
    """BUSINESS: UMBS 30 on 2026-11-25: 10-year 4.85 + 1.35 = 6.20 current coupon;
    the 6.0 coupon is 0.20 below it, so 100 - 6 x 0.20 = 98.80, which is 98-25.6
    32nds, shown on the nearest half 32nd as 98-25+. Decimals arrive as strings."""
    umbs = grid["products"][0]
    assert umbs["anchor_tenor"] == "10Y" and umbs["anchor_yield_pct"] == "4.85"
    assert umbs["current_coupon_pct"] == "6.20"
    assert umbs["traded_low_pct"] == "2.20" and umbs["traded_high_pct"] == "8.20"
    cell = next(c for c in umbs["months"][0]["cells"] if c["coupon"] == "6.0")
    assert cell == {"coupon": "6.0", "price": "98.796875", "price_32nds": "98-25+", "model_only": False}
    assert Decimal(cell["price"]) == Decimal("98") + Decimal("25.5") / 32


def test_model_only_flags_reach_the_api(grid: dict) -> None:
    """BUSINESS: 1.0 is far below the market on UMBS 30, 6.0 is traded."""
    cells = {c["coupon"]: c for c in grid["products"][0]["months"][0]["cells"]}
    assert cells["1.0"]["model_only"] and not cells["6.0"]["model_only"]


def test_payups_in_32nds_with_labels(grid: dict) -> None:
    """BUSINESS: LLB 85K on UMBS 30: 0 at 4.0 (discount), the full 64/32 = "2-00"
    at 7.5 (premium). Labels match the Loan Tape's ("LLB 85K", "Low FICO")."""
    llb = next(p for p in grid["payups"] if p["product"] == "UMBS 30" and p["story"] == "LLB_85K")
    cells = {c["coupon"]: c for c in llb["cells"]}
    assert llb["story_label"] == "LLB 85K" and llb["full_32nds"] == "64"
    assert cells["4.0"] == {"coupon": "4.0", "payup_32nds": "0.0", "payup_text": "0-00"}
    assert cells["7.5"]["payup_32nds"] == "64.0" and cells["7.5"]["payup_text"] == "2-00"
    labels = {p["story_label"] for p in grid["payups"]}
    assert {"Low FICO", "NY", "PR"} <= labels
    assert len(grid["payups"]) == 72


def test_sources_are_listed(grid: dict) -> None:
    """BUSINESS: the screen can say where the numbers come from: Treasury, and
    LoanIQ's own illustrative model."""
    names = [s["name"] for s in grid["sources"]]
    assert names[0].startswith("U.S. Treasury")
    assert grid["sources"][0]["url"] == "https://home.treasury.gov/treasury-daily-interest-rate-xml-feed"
    assert grid["sources"][1]["url"] is None


def test_label_says_when_treasury_is_down() -> None:
    """BUSINESS: with no curve ever fetched, the label says it is the bundled
    sample curve, not today's."""
    down = FakeTreasury()
    down.down = True
    service = main.build_pricing(slotting_rules(), load_slotting_words(), down)
    body = client_for(service).get("/api/prices/grid").json()
    assert body["curve_status"] == "fixture" and body["curve_fetched_at"] is None
    assert body["label"].startswith("Illustrative, as of 2026-11-25. Treasury could not be reached")
    assert "bundled sample curve" in body["label"]


def test_label_for_a_kept_curve() -> None:
    """BUSINESS: Treasury down after an earlier fetch: the label says so."""
    fake, clock = FakeTreasury(), Clock(utc(2026, 11, 27, 15, 0))
    cfg = pricing_config()
    service = pricing_api.PricingService(build_price_source(cfg, fake, clock),
                                         pricing_api.load_pricing_words(), {})
    client = client_for(service)
    client.get("/api/prices/grid")
    fake.down, clock.now = True, utc(2026, 11, 28, 15, 0)
    body = client.get("/api/prices/grid").json()
    assert body["curve_status"] == "cached"
    assert "last curve LoanIQ fetched" in body["label"]


@pytest.mark.parametrize("source", [FilePriceSource(), VendorPriceSource()])
def test_stub_sources_answer_503(source: FilePriceSource | VendorPriceSource) -> None:
    """BUSINESS: a desk file or vendor feed is not built yet; the API says so
    rather than inventing prices."""
    with pytest.raises(PriceSourceNotConfigured):
        source.price_file()
    service = pricing_api.PricingService(source, pricing_api.load_pricing_words(), {})
    response = client_for(service).get("/api/prices/grid")
    assert response.status_code == 503 and "not configured" in response.json()["detail"]


def test_build_price_source_picks_by_config() -> None:
    """TECH: pricing.toml [source] active -> the matching strategy."""
    cfg = pricing_config()
    assert isinstance(build_price_source(cfg, FakeTreasury()), ModelPriceSource)
    assert isinstance(build_price_source(replace_source(cfg, "file")), FilePriceSource)
    assert isinstance(build_price_source(replace_source(cfg, "vendor")), VendorPriceSource)


def replace_source(cfg, name: str):  # noqa: ANN001, ANN201 - PricingConfig in and out
    """The config with another [source] active."""
    return replace(cfg, source=name)


def test_no_pricing_service_is_503() -> None:
    """TECH: an app built without slotting rules has no prices (main.build_pricing
    returns None), and the route says so instead of crashing."""
    assert main.build_pricing(None, {}, None) is None
    assert client_for(None).get("/api/prices/grid").status_code == 503


def test_route_is_in_the_openapi_spec() -> None:
    """TECH: the screen's TypeScript types are generated from this spec."""
    spec = main.app.openapi()
    assert "/api/prices/grid" in spec["paths"]
    assert "PriceGrid" in spec["components"]["schemas"]
