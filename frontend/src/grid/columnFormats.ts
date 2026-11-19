/**
 * grid/columnFormats.ts: how each kind of number and date is displayed.
 *
 * Where it sits: /api/loans/columns -> loanColumns.ts (column definitions)
 * -> [columnFormats] -> each cell's text, plus the KPI tiles.
 *
 * BUSINESS: traders read numbers at a glance, so each kind always looks the same:
 *   money  $  412,350          commas, no cents (a tape is read in whole dollars)
 *   rate   %  6.375            3 decimals: note rates move in eighths (0.125)
 *                              and sixteenths, so 6.375 and 6.38 are different loans
 *   ratio  %  80.00            LTV family and DTI, 2 decimals
 *   date      2026-11-18       YYYY-MM-DD, sorts the same way it reads
 *   count     742, 360         whole numbers (FICO, months, units)
 *   points    5.00             ARM rate caps, in percentage points
 * TECH: COLUMN_FORMATS names the columns that need a special format; every other
 *   number is a count and every other date a date. Display only: the grid sorts and
 *   filters on the raw values from the API. Intl.NumberFormat objects are built once
 *   because creating them is slow, and the grid formats thousands of cells.
 *   null or undefined (for example margin on a fixed-rate loan) shows as blank.
 */

export type NumberFormat = "money" | "rate" | "ratio" | "count" | "points";

/** TECH: the columns whose format is not the default for their kind. */
export const COLUMN_FORMATS: Record<string, NumberFormat> = {
  orig_upb: "money",
  current_upb: "money",
  pi_payment: "money",
  appraised_value: "money",
  current_value: "money",
  note_rate: "rate",
  margin: "rate",
  ltv: "ratio",
  cltv: "ratio",
  hcltv: "ratio",
  mtm_ltv: "ratio",
  dti: "ratio",
  initial_cap: "points",
  periodic_cap: "points",
  lifetime_cap: "points",
};

/** TECH: en-US formatters, one per format, built once. */
const FORMATTERS: Record<NumberFormat, Intl.NumberFormat> = {
  money: new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }),
  rate: new Intl.NumberFormat("en-US", { minimumFractionDigits: 3, maximumFractionDigits: 3 }),
  ratio: new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
  count: new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }),
  points: new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
};

/**
 * Format one number.
 * BUSINESS: formatNumber(412350.67, "money") -> "412,351"; (6.375, "rate") -> "6.375".
 * TECH: blank for null, undefined or a non-number (never "NaN" on a desk screen).
 *   Money rounds half away from zero to the dollar, as Intl does.
 */
export function formatNumber(value: unknown, format: NumberFormat): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "";
  return FORMATTERS[format].format(value);
}

/**
 * Format a date as YYYY-MM-DD.
 * TECH: the API already sends "2026-11-18"; a longer ISO timestamp is cut to its date
 *   part. Parsing with new Date() is avoided on purpose: it shifts dates by the
 *   browser's time zone, which can move a maturity date back one day.
 */
export function formatDate(value: unknown): string {
  if (typeof value !== "string") return "";
  return /^\d{4}-\d{2}-\d{2}/.test(value) ? value.slice(0, 10) : value;
}

/** BUSINESS: flags (first-time buyer, modified, forbearance) read Yes or No. */
export function formatBoolean(value: unknown): string {
  if (value === true) return "Yes";
  if (value === false) return "No";
  return "";
}

/** TECH: the number format for a column, falling back to a whole-number count. */
export function numberFormatFor(column: string): NumberFormat {
  return COLUMN_FORMATS[column] ?? "count";
}
