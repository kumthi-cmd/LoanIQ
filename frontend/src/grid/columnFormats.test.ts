/**
 * Tests for grid/columnFormats.ts.
 * BUSINESS: a trader reads these numbers at a glance; each test protects one display
 *   rule: money in whole dollars with commas, rates to 3 decimals (eighths and
 *   sixteenths must stay distinct), LTV and DTI to 2, dates as YYYY-MM-DD, and no
 *   "NaN" or "null" ever on screen.
 */
import { describe, expect, it } from "vitest";
import { formatBoolean, formatDate, formatNumber, numberFormatFor } from "./columnFormats";

describe("formatNumber", () => {
  it("shows money with commas and no cents", () => {
    expect(formatNumber(412350.67, "money")).toBe("412,351");
    expect(formatNumber(1234567890.4, "money")).toBe("1,234,567,890");
    expect(formatNumber(0, "money")).toBe("0");
  });

  it("shows rates with exactly 3 decimals so 6.375 and 6.38 differ", () => {
    expect(formatNumber(6.375, "rate")).toBe("6.375");
    expect(formatNumber(6.38, "rate")).toBe("6.380");
    expect(formatNumber(7, "rate")).toBe("7.000");
  });

  it("shows LTV and DTI ratios with 2 decimals", () => {
    expect(formatNumber(80, "ratio")).toBe("80.00");
    expect(formatNumber(125.456, "ratio")).toBe("125.46");
  });

  it("shows counts as whole numbers and caps with 2 decimals", () => {
    expect(formatNumber(742, "count")).toBe("742");
    expect(formatNumber(12345, "count")).toBe("12,345");
    expect(formatNumber(5, "points")).toBe("5.00");
  });

  it("shows blank, never NaN, for missing values", () => {
    for (const v of [null, undefined, Number.NaN, "6.5", Infinity]) {
      expect(formatNumber(v, "rate")).toBe("");
    }
  });
});

describe("formatDate", () => {
  it("keeps YYYY-MM-DD and cuts timestamps to the date", () => {
    expect(formatDate("2026-11-18")).toBe("2026-11-18");
    expect(formatDate("2051-11-01T00:00:00")).toBe("2051-11-01");
  });

  it("does not shift dates by time zone", () => {
    // BUSINESS: a maturity date of the 1st must never show as the 31st.
    expect(formatDate("2051-01-01")).toBe("2051-01-01");
  });

  it("shows blank for missing dates", () => {
    expect(formatDate(null)).toBe("");
    expect(formatDate(undefined)).toBe("");
  });
});

describe("formatBoolean", () => {
  it("shows flags as Yes and No", () => {
    expect(formatBoolean(true)).toBe("Yes");
    expect(formatBoolean(false)).toBe("No");
    expect(formatBoolean(null)).toBe("");
  });
});

describe("numberFormatFor", () => {
  it("maps tape columns to their format", () => {
    expect(numberFormatFor("current_upb")).toBe("money");
    expect(numberFormatFor("pi_payment")).toBe("money");
    expect(numberFormatFor("note_rate")).toBe("rate");
    expect(numberFormatFor("margin")).toBe("rate");
    for (const c of ["ltv", "cltv", "hcltv", "mtm_ltv", "dti"]) expect(numberFormatFor(c)).toBe("ratio");
    expect(numberFormatFor("fico")).toBe("count");
    expect(numberFormatFor("loan_age")).toBe("count");
  });
});
