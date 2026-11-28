/**
 * pricing/priceGridView.ts: turns the price file from the API into what the Price
 * Grid screen draws (Step 6c).
 *
 * Where it sits: GET /api/prices/grid (api/client.ts) -> [priceGridView] ->
 *   PriceTable, PayupTable, ProductCard -> the Price Grid screen.
 *
 * BUSINESS: the desk reads a price file a few ways at once:
 *   - which coupons trade today (the traded band), and which the model only prices;
 *   - which coupon sits nearest each product's current coupon (the one that trades
 *     closest to par), so the eye lands there first;
 *   - pay-ups quoted in 32nds the way traders say them ("18+" = 18.5/32);
 *   - SIFMA's dates as short day-month labels ("08 Dec").
 * TECH:
 *   - Plain functions with no React, so each rule has its own unit test
 *     (priceGridView.test.ts). They never do price arithmetic: every price, drop and
 *     pay-up comes from the back end already rounded. The one number worked here is
 *     the distance from a coupon to the current coupon, only to pick the nearest.
 *   - The API sends Decimals as strings ("6.29"); Number() is safe for the nearest
 *     coupon test because coupons step by 0.5 and the gap needs no exact cents.
 *   - Which coupons trade comes from the back end's model_only flag, so the band is
 *     defined once, in backend/app/config/pricing.toml, never recomputed here.
 */
import type { PayupRow, PriceCell, PriceGrid, ProductRow } from "../api/types";

/** BUSINESS: the table's two views: the coupons that trade today, or all of them. */
export type CouponView = "traded" | "all";

/**
 * A product's Current-month cells (the first, and today the only, month).
 * BUSINESS: since Step 6b the grid has one Current column per product.
 * TECH: returns [] for a product with no months, so a malformed row draws empty
 *   cells instead of crashing the screen.
 */
export function currentCells(product: ProductRow): PriceCell[] {
  return product.months[0]?.cells ?? [];
}

/**
 * The coupons at least one product trades today, in the grid's order.
 * BUSINESS: "Traded coupons" view: from the lowest coupon any product trades to the
 *   highest (UMBS 30 on 2026-11-27: 2.5 to 8.0). Coupons no product trades are
 *   deep discounts or premiums with no market.
 * TECH: a coupon is traded for a product when its cell is not model_only.
 */
export function tradedCoupons(grid: PriceGrid): string[] {
  const traded = new Set<string>();
  for (const p of grid.products) {
    for (const c of currentCells(p)) if (!c.model_only) traded.add(c.coupon);
  }
  return grid.coupons.filter((c) => traded.has(c));
}

/**
 * The coupons one product trades today, in the grid's order.
 * BUSINESS: the pay-up table's columns in the "Traded coupons" view: a spec story
 *   is only worth quoting on a coupon that trades.
 */
export function productTradedCoupons(product: ProductRow): string[] {
  return currentCells(product).filter((c) => !c.model_only).map((c) => c.coupon);
}

/**
 * The grid coupon nearest the product's current coupon.
 * BUSINESS: the current coupon (6.29% for UMBS 30) is rarely a coupon that trades;
 *   the nearest one (6.5) is the TBA closest to par, where a desk looks first.
 * TECH: distance |coupon - current coupon| in percent. A tie (current coupon exactly
 *   halfway, say 6.25) goes to the lower coupon, the first one met. null when the
 *   grid has no coupons.
 */
export function nearestCoupon(coupons: readonly string[], currentCouponPct: string): string | null {
  const cc = Number(currentCouponPct);
  let best: string | null = null;
  for (const c of coupons) {
    if (best === null || Math.abs(Number(c) - cc) < Math.abs(Number(best) - cc)) best = c;
  }
  return best;
}

/** One cell of the price table: the API's cell and whether it is the nearest coupon. */
export interface PriceTableCell {
  product: string;
  cell: PriceCell | undefined;
  nearest: boolean;
}

/** One row of the price table: a coupon, then one cell per product. */
export interface PriceTableRow {
  coupon: string;
  cells: PriceTableCell[];
}

/**
 * The price table's rows for the chosen view.
 * BUSINESS: coupons down the side, products across; each cell is that product's
 *   Current price and drop at that coupon.
 * TECH: cells are matched by coupon string, not by position, so a product that
 *   lacks a coupon shows an empty cell instead of shifting the row.
 */
export function priceTableRows(grid: PriceGrid, view: CouponView): PriceTableRow[] {
  const coupons = view === "traded" ? tradedCoupons(grid) : grid.coupons;
  const byProduct = grid.products.map((p) => ({
    name: p.name,
    cells: new Map(currentCells(p).map((c) => [c.coupon, c])),
    nearest: nearestCoupon(grid.coupons, p.current_coupon_pct),
  }));
  return coupons.map((coupon) => ({
    coupon,
    cells: byProduct.map((p) => ({ product: p.name, cell: p.cells.get(coupon), nearest: p.nearest === coupon })),
  }));
}

/**
 * One product's pay-up rows, in the API's order (LLB tiers, then NY, PR, Low FICO).
 * BUSINESS: the stories that can be delivered on that product.
 */
export function payupRowsFor(grid: PriceGrid, product: string): PayupRow[] {
  return grid.payups.filter((r) => r.product === product);
}

/**
 * A pay-up in 32nds as a trader says it.
 * BUSINESS: 18.5 -> "18+", 64 -> "64" (two points), 0 -> "0". The "+" is half a 32nd,
 *   as in prices ("98-08+").
 * TECH: the API rounds pay-ups to half a 32nd, so the value is a whole number or a
 *   half. Anything else (it should not happen) is shown as sent.
 */
export function formatPayup32nds(payup32nds: string): string {
  const v = Number(payup32nds);
  if (!Number.isFinite(v)) return payup32nds;
  const whole = Math.floor(v);
  const half = v - whole;
  if (half === 0) return String(whole);
  if (half === 0.5) return `${whole}+`;
  return payup32nds;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

/**
 * Split an ISO date ("2026-12-08") into numbers.
 * TECH: read by hand instead of new Date("2026-12-08"), which JavaScript treats as
 *   midnight UTC and can show as the day before in New York. null for anything else.
 */
function isoParts(iso: string): { y: number; m: number; d: number } | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!match) return null;
  return { y: Number(match[1]), m: Number(match[2]), d: Number(match[3]) };
}

/**
 * BUSINESS: a SIFMA date on a product card: "2026-12-08" -> "08 Dec".
 * TECH: the input is returned unchanged if it is not an ISO date.
 */
export function shortDate(iso: string): string {
  const p = isoParts(iso);
  return p ? `${String(p.d).padStart(2, "0")} ${MONTHS[p.m - 1]}` : iso;
}

/**
 * BUSINESS: the trade or curve date in the header strip: "2026-11-27" -> "Fri 27 Nov 2026".
 * TECH: the weekday comes from Date.UTC, which cannot shift by time zone.
 */
export function longDate(iso: string): string {
  const p = isoParts(iso);
  if (!p) return iso;
  const weekday = WEEKDAYS[new Date(Date.UTC(p.y, p.m - 1, p.d)).getUTCDay()];
  return `${weekday} ${p.d} ${MONTHS[p.m - 1]} ${p.y}`;
}

/**
 * BUSINESS: a rate the API sends as a Decimal string, with LoanIQ's three decimals
 *   (.claude/rules/frontend.md): "6.29" -> "6.290", "1.2" -> "1.200". Used for the
 *   current coupon, the anchor yield, its spread and the financing rate.
 * TECH: the back end's rates have two places or fewer (Treasury quotes to 0.01), so
 *   toFixed(3) only pads; it never rounds a real digit away. Text that is not a
 *   number is returned unchanged.
 */
export function rate3(value: string): string {
  const v = Number(value);
  return value.trim() !== "" && Number.isFinite(v) ? v.toFixed(3) : value;
}
