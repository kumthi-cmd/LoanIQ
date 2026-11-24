/**
 * Tests for grid/loanColumns.ts.
 * BUSINESS: the grid's columns follow the desk's display rules: loan_id always
 *   visible, numbers right-aligned and formatted by kind, only filters the server
 *   understands, header tooltips from the glossary, and delinquent loans in red.
 */
import type { CellClassParams, ColDef, ValueFormatterParams } from "ag-grid-community";
import { describe, expect, it } from "vitest";
import type { ColumnInfo, LoanRow } from "../api/types";
import { DEFAULT_COLUMN_WIDTHS, DEFAULT_VISIBLE_COLUMNS } from "./gridConfig";
import { buildColumnDefs, isDelinquent, NUMBER_FILTER_OPTIONS, TEXT_FILTER_OPTIONS } from "./loanColumns";

const COLUMNS: ColumnInfo[] = [
  { name: "loan_id", type: "VARCHAR", kind: "text", label: "Loan ID" },
  { name: "current_upb", type: "DECIMAL(14,2)", kind: "number", label: "Current UPB ($)" },
  { name: "note_rate", type: "DOUBLE", kind: "number", label: "Note Rate (%)" },
  { name: "ltv", type: "DOUBLE", kind: "number", label: "LTV (%)" },
  { name: "orig_date", type: "DATE", kind: "date", label: "Origination Date" },
  { name: "mod_flag", type: "BOOLEAN", kind: "boolean", label: "Modified" },
  { name: "dq_status", type: "VARCHAR", kind: "text", label: "DQ Status" },
  { name: "property_type", type: "VARCHAR", kind: "text", label: "Property Type" },
];

const defs = buildColumnDefs(COLUMNS);
const byName = (n: string) => defs.find((d) => d.field === n)!;

// TECH: call a column's valueFormatter the way AG Grid would.
function show(def: ColDef<LoanRow>, value: unknown): string {
  const fmt = def.valueFormatter as (p: ValueFormatterParams<LoanRow>) => string;
  return fmt({ value } as ValueFormatterParams<LoanRow>);
}

describe("buildColumnDefs", () => {
  it("keeps tape order and readable headers", () => {
    expect(defs.map((d) => d.field)).toEqual(COLUMNS.map((c) => c.name));
    expect(byName("current_upb").headerName).toBe("Current UPB ($)");
  });

  it("pins loan_id on the left and nothing else", () => {
    expect(byName("loan_id").pinned).toBe("left");
    expect(defs.filter((d) => d.pinned)).toHaveLength(1);
  });

  it("right-aligns numbers only", () => {
    expect(byName("current_upb").type).toBe("rightAligned");
    expect(byName("ltv").type).toBe("rightAligned");
    expect(byName("property_type").type).toBeUndefined();
  });

  it("formats each column by its kind", () => {
    expect(show(byName("current_upb"), 412350.67)).toBe("412,351");
    expect(show(byName("note_rate"), 6.5)).toBe("6.500");
    expect(show(byName("ltv"), 80)).toBe("80.00");
    expect(show(byName("orig_date"), "2021-10-28")).toBe("2021-10-28");
    expect(show(byName("mod_flag"), true)).toBe("Yes");
  });

  it("offers only the filters the API accepts", () => {
    // TECH: anything else would come back from the server as HTTP 400.
    expect(byName("ltv").filter).toBe("agNumberColumnFilter");
    expect(byName("ltv").filterParams.filterOptions).toEqual(NUMBER_FILTER_OPTIONS);
    expect(byName("property_type").filter).toBe("agTextColumnFilter");
    expect(byName("property_type").filterParams.filterOptions).toEqual(TEXT_FILTER_OPTIONS);
    expect(byName("orig_date").filter).toBe(false);
    expect(byName("mod_flag").filter).toBe(false);
  });

  it("every column can be sorted on the server", () => {
    expect(defs.every((d) => d.sortable)).toBe(true);
  });

  it("explains glossary-backed headers on hover", () => {
    expect(byName("ltv").headerTooltip).toMatch(/Why it matters/);
    expect(byName("dq_status").headerTooltip).toBeTruthy();
    expect(byName("property_type").headerTooltip).toBeUndefined();
  });

  it("marks dq_status red unless it is Current", () => {
    const rule = byName("dq_status").cellClassRules!["dq-delinquent"] as (p: CellClassParams<LoanRow>) => boolean;
    const red = (value: unknown) => rule({ value } as CellClassParams<LoanRow>);
    expect(red("Current")).toBe(false);
    for (const s of ["30", "60", "90", "120+", "FC", "BK", "REO"]) expect(red(s)).toBe(true);
    expect(byName("property_type").cellClassRules).toBeUndefined();
  });
});

describe("isDelinquent", () => {
  it("treats every MBA status except Current as delinquent, and blank as unknown", () => {
    expect(isDelinquent("Current")).toBe(false);
    expect(isDelinquent("90")).toBe(true);
    expect(isDelinquent(null)).toBe(false);
    expect(isDelinquent("")).toBe(false);
  });
});

describe("buildColumnDefs with hidden columns", () => {
  it("hides the named columns but never the loan ID", () => {
    // BUSINESS: the loan ID always stays so every row can be identified.
    const hidden = buildColumnDefs(COLUMNS, new Set(["ltv", "loan_id"]));
    const hide = (n: string) => hidden.find((d) => d.field === n)!.hide;
    expect(hide("ltv")).toBe(true);
    expect(hide("loan_id")).toBe(false);
    expect(hide("note_rate")).toBe(false);
  });

  it("shows every column by default, and loan IDs in a monospace font", () => {
    expect(defs.every((d) => d.hide === false)).toBe(true);
    expect(byName("loan_id").cellClass).toBe("cell-mono");
  });
});

describe("buildColumnDefs default widths (Step 1g)", () => {
  // BUSINESS: the default columns start fitted to their content, so all 12 show at
  //   1440 px with the explanation closed (e2e/tests/loan-tape-layout.spec.ts checks
  //   that in a real browser).
  it("starts each default column at its configured width, and no narrower", () => {
    expect(byName("loan_id").width).toBe(DEFAULT_COLUMN_WIDTHS.loan_id);
    expect(byName("note_rate").width).toBe(DEFAULT_COLUMN_WIDTHS.note_rate);
    expect(byName("ltv").minWidth).toBe(DEFAULT_COLUMN_WIDTHS.ltv);
  });

  // TECH: a column with no configured width keeps the grid default (LoanGrid.tsx).
  it("leaves other columns to the grid default", () => {
    expect(byName("orig_date").width).toBeUndefined();
    expect(byName("property_type").minWidth).toBeUndefined();
  });

  // BUSINESS: every default column has a width, and they add up to less than the
  //   grid's width at 1440 px with the explanation closed (about 1,150 px).
  it("sizes all 12 default columns within the 1440 px budget", () => {
    expect(Object.keys(DEFAULT_COLUMN_WIDTHS).sort()).toEqual([...DEFAULT_VISIBLE_COLUMNS].sort());
    const total = Object.values(DEFAULT_COLUMN_WIDTHS).reduce((a, b) => a + b, 0);
    expect(total).toBeLessThanOrEqual(1150);
  });
});
