/**
 * pricing/priceGridFixture.ts: a small price file for the Price Grid tests (Step 6c).
 *
 * Where it sits: test files only -> [fixture] stands in for GET /api/prices/grid.
 *
 * BUSINESS: two products and five coupons, copied from the live price file of
 *   2026-11-27 (curve: 10-year 4.94, 5-year 4.74; Current = December 2026):
 *   - UMBS 30, current coupon 6.29: nearest coupon 6.5 (0.21 away; 6.0 is 0.29);
 *   - UMBS 15, current coupon 5.74: nearest coupon 5.5 (0.24 away; 6.0 is 0.26);
 *   - 2.0 and 8.5 are model-only on both, so "Traded coupons" is 5.5, 6.0, 6.5;
 *   - the 2.0 drops are negative (next month trades higher), as on the live file.
 *   Prices in 32nds and in points agree: 98-08+ = 98 + 8.5/32 = 98.265625.
 * TECH: typed as the generated PriceGrid, so a change to the API's shape breaks the
 *   tests at compile time instead of passing on stale data. Hand-written and small,
 *   so every expectation in a test can be checked by eye.
 */
import type { PayupRow, PriceCell, PriceGrid, ProductRow } from "../api/types";

/** TECH: one cell from its coupon, price, drop and model-only flag. */
function cell(coupon: string, price: string, price32: string, drop: string, drop32: string, dropText: string,
  modelOnly = false): PriceCell {
  return { coupon, price, price_32nds: price32, drop, drop_32nds: drop32, drop_text: dropText, model_only: modelOnly };
}

export const UMBS30: ProductRow = {
  name: "UMBS 30", agency: "UMBS", term: "30Y Fixed", anchor_tenor: "10Y", anchor_yield_pct: "4.94",
  spread_pct: "1.35", current_coupon_pct: "6.29", traded_low_pct: "2.29", traded_high_pct: "8.29",
  months: [{
    month: "Current", label: "Dec 2026", sifma_class: "A", notification_date: "2026-12-08",
    settlement_date: "2026-12-10", next_label: "Jan 2027", next_settlement_date: "2027-01-14", days: 35,
    financing_rate_pct: "4.27",
    cells: [
      cell("2.0", "74.265625", "74-08+", "-0.015625", "-0.5", "-0-00+", true),
      cell("5.5", "95.265625", "95-08+", "0.09375", "3.0", "0-03"),
      cell("6.0", "98.265625", "98-08+", "0.109375", "3.5", "0-03+"),
      cell("6.5", "101.109375", "101-03+", "0.109375", "3.5", "0-03+"),
      cell("8.5", "104.640625", "104-20+", "0.15625", "5.0", "0-05", true),
    ],
  }],
};

export const UMBS15: ProductRow = {
  name: "UMBS 15", agency: "UMBS", term: "15Y Fixed", anchor_tenor: "5Y", anchor_yield_pct: "4.74",
  spread_pct: "1.0", current_coupon_pct: "5.74", traded_low_pct: "2.74", traded_high_pct: "7.24",
  months: [{
    month: "Current", label: "Dec 2026", sifma_class: "B", notification_date: "2026-12-11",
    settlement_date: "2026-12-15", next_label: "Jan 2027", next_settlement_date: "2027-01-19", days: 35,
    financing_rate_pct: "4.27",
    cells: [
      cell("2.0", "85.046875", "85-01+", "-0.109375", "-3.5", "-0-03+", true),
      cell("5.5", "99.046875", "99-01+", "0.0625", "2.0", "0-02"),
      cell("6.0", "100.875", "100-28", "0.0625", "2.0", "0-02"),
      cell("6.5", "101.90625", "101-29", "0.078125", "2.5", "0-02+"),
      cell("8.5", "102.921875", "102-29+", "0.21875", "7.0", "0-07", true),
    ],
  }],
};

/** TECH: one pay-up row from its full size and the five coupons' pay-ups, in 32nds. */
function payups(product: string, story: string, label: string, family: string, full: string,
  values: [string, string][]): PayupRow {
  return {
    product, story, story_label: label, family, full_32nds: full,
    cells: values.map(([coupon, v]) => ({ coupon, payup_32nds: v, payup_text: "" })),
  };
}

export const COUPONS = ["2.0", "5.5", "6.0", "6.5", "8.5"];

export const PRICE_GRID: PriceGrid = {
  as_of: "2026-11-27",
  trade_date: "2026-11-27",
  label: "Illustrative, as of 2026-11-27",
  curve_status: "live",
  curve_fetched_at: "2026-11-27T15:00:00Z",
  price_source: "model",
  illustrative: true,
  months: ["Current"],
  coupons: COUPONS,
  products: [UMBS30, UMBS15],
  // BUSINESS: the S-curve: nothing on the 2.0 discount, the full size on the 8.5 premium.
  payups: [
    payups("UMBS 30", "LLB_85K", "LLB 85K", "LLB", "64",
      [["2.0", "0.0"], ["5.5", "2.0"], ["6.0", "18.5"], ["6.5", "42.0"], ["8.5", "64.0"]]),
    payups("UMBS 30", "NY", "NY", "NY", "12",
      [["2.0", "0.0"], ["5.5", "0.5"], ["6.0", "3.5"], ["6.5", "8.0"], ["8.5", "12.0"]]),
    payups("UMBS 15", "LLB_85K", "LLB 85K", "LLB", "64",
      [["2.0", "0.0"], ["5.5", "20.5"], ["6.0", "44.0"], ["6.5", "61.5"], ["8.5", "64.0"]]),
  ],
  sources: [
    { name: "U.S. Treasury, Daily Treasury Par Yield Curve Rates", url: "https://home.treasury.gov/treasury-daily-interest-rate-xml-feed",
      used_for: "The daily anchor." },
    { name: "LoanIQ illustrative pricing model", url: null, used_for: "Spreads and the rest." },
    { name: "SIFMA, MBS Notification and Settlement Dates", url: "https://www.sifma.org/resources/general/mbs-notification-and-settlement-dates/",
      used_for: "The Current month." },
  ],
};
