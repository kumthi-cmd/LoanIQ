/**
 * Tests for ask/loanTapeUrl.ts: "Open in Loan Tape" links, out and back in.
 *
 * BUSINESS: protects "the same filter": the link an answer makes must come back as
 *   the same filter and sort in the Loan Tape, and an edited or broken URL must never
 *   filter the grid on something nobody asked for.
 * TECH: pure functions over URLSearchParams.
 */
import { describe, expect, it } from "vitest";
import { columnsInUse, loanTapeUrl, readLoanTapeParams } from "./loanTapeUrl";

const COLUMNS = ["loan_id", "ltv", "state", "current_upb"];
const LTV = { ltv: { filterType: "number", type: "greaterThan", filter: 125 } };

describe("loanTapeUrl", () => {
  it("round-trips a filter and sort through the URL", () => {
    const url = loanTapeUrl({ filter: LTV, sort: "ltv:desc", reason: null });
    expect(url).toMatch(/^\/\?filter=/);
    const back = readLoanTapeParams(new URLSearchParams(url!.split("?")[1]), [], COLUMNS);
    expect(back.filter).toEqual(LTV);
    expect(back.sort).toEqual([{ colId: "ltv", sort: "desc" }]);
    expect(columnsInUse(back)).toEqual(["ltv", "ltv"]);
  });

  it("opens the whole tape for an empty filter, and nothing when it cannot open", () => {
    expect(loanTapeUrl({ filter: {}, sort: null, reason: null })).toBe("/");
    expect(loanTapeUrl({ filter: null, sort: null, reason: "uses OR" })).toBeNull();
    expect(loanTapeUrl(null)).toBeNull();
  });
});

describe("readLoanTapeParams", () => {
  it("ignores what it cannot trust: bad JSON, arrays, unknown sort columns and chips", () => {
    const p = readLoanTapeParams(
      new URLSearchParams({ filter: "[1,2]", sort: "ltv:sideways,drop_table:asc,state:asc", question: "nope" }),
      ["ltv_over_125"], COLUMNS);
    expect(p).toEqual({ filter: null, sort: [{ colId: "state", sort: "asc" }], question: null });
    expect(readLoanTapeParams(new URLSearchParams("filter={oops"), [], COLUMNS).filter).toBeNull();
  });

  it("accepts a known desk question", () => {
    expect(readLoanTapeParams(new URLSearchParams("question=ltv_over_125"), ["ltv_over_125"], COLUMNS).question)
      .toBe("ltv_over_125");
  });
});
