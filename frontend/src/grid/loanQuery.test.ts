/**
 * Tests for grid/loanQuery.ts.
 * BUSINESS: what the trader asks the grid for ("rows 200-299, largest balance first,
 *   LTV over 125") must reach the server exactly, or the grid shows the wrong loans.
 */
import { describe, expect, it } from "vitest";
import { buildLoansQuery } from "./loanQuery";

const base = { startRow: 0, endRow: 100, sortModel: [], filterModel: null };

describe("buildLoansQuery", () => {
  it("turns a block of rows into offset and limit", () => {
    const q = buildLoansQuery({ ...base, startRow: 200, endRow: 300 });
    expect(q.get("offset")).toBe("200");
    expect(q.get("limit")).toBe("100");
  });

  it("leaves out sort and filter when there are none (server default order)", () => {
    const q = buildLoansQuery({ ...base, filterModel: {} });
    expect(q.has("sort")).toBe(false);
    expect(q.has("filter")).toBe(false);
  });

  it("sends multi-column sorts in the grid's order", () => {
    const q = buildLoansQuery({
      ...base,
      sortModel: [
        { colId: "current_upb", sort: "desc" },
        { colId: "fico", sort: "asc" },
      ],
    });
    expect(q.get("sort")).toBe("current_upb:desc,fico:asc");
  });

  it("sends the AG Grid filter model unchanged as JSON", () => {
    // BUSINESS: LTV over 125 and New York only.
    const filterModel = {
      ltv: { filterType: "number", type: "greaterThan", filter: 125 },
      state: { filterType: "text", type: "equals", filter: "NY" },
    };
    const q = buildLoansQuery({ ...base, filterModel });
    expect(JSON.parse(q.get("filter")!)).toEqual(filterModel);
  });

  it("escapes filter text safely in the URL", () => {
    // TECH: quotes, ampersands and SQL-looking text travel as data, not URL syntax.
    const filterModel = { seller: { filterType: "text", type: "contains", filter: "a&b=' OR 1=1 --" } };
    const text = buildLoansQuery({ ...base, filterModel }).toString();
    expect(text).not.toContain("&b=");
    expect(JSON.parse(new URLSearchParams(text).get("filter")!)).toEqual(filterModel);
  });
});

describe("buildLoansQuery with a desk question", () => {
  const req = { startRow: 0, endRow: 100, sortModel: [], filterModel: null };

  it("sends the chip's question id alongside paging", () => {
    // BUSINESS: "LTV over 125" clicked -> the server applies its rule to the whole tape.
    const q = buildLoansQuery(req, "ltv_over_125");
    expect(q.get("question")).toBe("ltv_over_125");
    expect(q.get("offset")).toBe("0");
  });

  it("sends no question when no chip is on", () => {
    expect(buildLoansQuery(req).has("question")).toBe(false);
    expect(buildLoansQuery(req, null).has("question")).toBe(false);
    expect(buildLoansQuery(req, "").has("question")).toBe(false);
  });
});
