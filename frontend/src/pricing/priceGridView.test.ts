/**
 * Tests for pricing/priceGridView.ts: how the Price Grid reads the price file (Step 6c).
 *
 * BUSINESS: what a desk relies on when it reads the grid:
 *   - "Traded coupons" are exactly the coupons some product trades (the back end's
 *     traded band), never a range the screen made up;
 *   - the highlighted coupon is the one nearest each product's current coupon;
 *   - pay-ups read as traders say them ("18+"), and SIFMA's dates as "08 Dec";
 *   - rates show LoanIQ's three decimals.
 * TECH: plain function tests on the hand-written fixture (pricing/priceGridFixture.ts).
 */
import { describe, expect, it } from "vitest";
import {
  currentCells, formatPayup32nds, longDate, nearestCoupon, payupRowsFor, priceTableRows, productTradedCoupons,
  rate3, shortDate, tradedCoupons,
} from "./priceGridView";
import { COUPONS, PRICE_GRID, UMBS15, UMBS30 } from "./priceGridFixture";

describe("traded coupons", () => {
  // BUSINESS: 2.0 and 8.5 are model-only on both products, so they drop out.
  it("keeps the coupons at least one product trades, in grid order", () => {
    expect(tradedCoupons(PRICE_GRID)).toEqual(["5.5", "6.0", "6.5"]);
  });

  // BUSINESS: one product trading a coupon is enough to show it in the shared table.
  it("shows a coupon only one product trades", () => {
    const cells = currentCells(UMBS15).map((c) => (c.coupon === "8.5" ? { ...c, model_only: false } : c));
    const grid = { ...PRICE_GRID, products: [UMBS30, { ...UMBS15, months: [{ ...UMBS15.months[0], cells }] }] };
    expect(tradedCoupons(grid)).toEqual(["5.5", "6.0", "6.5", "8.5"]);
  });

  it("gives each product its own traded band for the pay-up table", () => {
    expect(productTradedCoupons(UMBS30)).toEqual(["5.5", "6.0", "6.5"]);
  });

  // TECH: a product with no months draws empty, not a crash.
  it("treats a product with no months as having no cells", () => {
    expect(currentCells({ ...UMBS30, months: [] })).toEqual([]);
  });
});

describe("nearest coupon", () => {
  // BUSINESS: UMBS 30 at 6.29 is nearest 6.5 (0.21 away; 6.0 is 0.29 away).
  it("picks the coupon closest to the current coupon", () => {
    expect(nearestCoupon(COUPONS, "6.29")).toBe("6.5");
    expect(nearestCoupon(COUPONS, "5.74")).toBe("5.5");
  });

  // BUSINESS: a current coupon exactly halfway goes to the lower coupon.
  it("breaks a tie toward the lower coupon", () => {
    expect(nearestCoupon(COUPONS, "6.25")).toBe("6.0");
  });

  it("is null for a grid with no coupons", () => {
    expect(nearestCoupon([], "6.29")).toBeNull();
  });
});

describe("price table rows", () => {
  it("has one row per traded coupon, one cell per product, nearest marked", () => {
    const rows = priceTableRows(PRICE_GRID, "traded");
    expect(rows.map((r) => r.coupon)).toEqual(["5.5", "6.0", "6.5"]);
    const at65 = rows.find((r) => r.coupon === "6.5")!;
    expect(at65.cells.map((c) => [c.product, c.cell?.price_32nds, c.nearest])).toEqual([
      ["UMBS 30", "101-03+", true],
      ["UMBS 15", "101-29", false],
    ]);
  });

  it("shows all coupons, model-only ones included, in the All view", () => {
    const rows = priceTableRows(PRICE_GRID, "all");
    expect(rows.map((r) => r.coupon)).toEqual(COUPONS);
    expect(rows[0].cells[0].cell?.model_only).toBe(true);
  });

  // TECH: cells match by coupon, so a missing coupon leaves a gap, not a shifted row.
  it("leaves a cell empty when a product lacks the coupon", () => {
    const cells = currentCells(UMBS15).filter((c) => c.coupon !== "6.0");
    const grid = { ...PRICE_GRID, products: [UMBS30, { ...UMBS15, months: [{ ...UMBS15.months[0], cells }] }] };
    const at60 = priceTableRows(grid, "all").find((r) => r.coupon === "6.0")!;
    expect(at60.cells[1].cell).toBeUndefined();
    expect(at60.cells[0].cell?.price_32nds).toBe("98-08+");
  });
});

describe("pay-ups", () => {
  it("keeps one product's stories in the API's order", () => {
    expect(payupRowsFor(PRICE_GRID, "UMBS 30").map((r) => r.story)).toEqual(["LLB_85K", "NY"]);
    expect(payupRowsFor(PRICE_GRID, "GNMA II 30")).toEqual([]);
  });

  // BUSINESS: traders say pay-ups in 32nds, "+" for a half.
  it.each([["18.5", "18+"], ["64.0", "64"], ["0.0", "0"], ["0.5", "0+"], ["2", "2"], ["abc", "abc"], ["1.25", "1.25"]])(
    "formats %s as %s", (value, text) => {
      expect(formatPayup32nds(value)).toBe(text);
    });
});

describe("dates and rates", () => {
  // TECH: "2026-12-08" must not become 07 Dec in a time zone west of UTC.
  it("shortens SIFMA dates without a time-zone shift", () => {
    expect(shortDate("2026-12-08")).toBe("08 Dec");
    expect(shortDate("2027-01-14")).toBe("14 Jan");
    expect(shortDate("not a date")).toBe("not a date");
  });

  it("writes the trade date with its weekday", () => {
    expect(longDate("2026-11-27")).toBe("Fri 27 Nov 2026");
    expect(longDate("2027-01-01")).toBe("Fri 1 Jan 2027");
    expect(longDate("")).toBe("");
  });

  // BUSINESS: rates with three decimals (.claude/rules/frontend.md).
  it("pads rates to three decimals without rounding a digit away", () => {
    expect(rate3("6.29")).toBe("6.290");
    expect(rate3("1.0")).toBe("1.000");
    expect(rate3("4.27")).toBe("4.270");
    expect(rate3("")).toBe("");
    expect(rate3("n/a")).toBe("n/a");
  });
});
