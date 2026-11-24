/**
 * Tests for components/ask/QueryResultTable.tsx (Step 4c: the default columns).
 *
 * BUSINESS: an answer about specific loans shows the trader's default fields
 *   (seller, program, coupon, balance, FICO, LTV, ...) beside the agent's own
 *   columns, in the Loan Tape's order and formats, so a trader can read each loan
 *   without opening the Loan Tape.
 * TECH: the server adds the columns (backend tools.add_base_columns); the table
 *   draws whatever columns the stored result has, in order. A rerun passes the rows
 *   as `initial`, so nothing is fetched here. Column widths are pure CSS
 *   (styles.css .result-table) and jsdom has no layout, so the packing itself is
 *   checked in a real browser by e2e/tests/ask-the-tape.spec.ts.
 */
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import type { ColumnInfo, StoredQuery } from "../../api/types";
import { QueryResultTable } from "./QueryResultTable";

// TECH: the 12 default tape columns, as GET /api/loans/columns describes them.
const INFO: ColumnInfo[] = [
  ["loan_id", "VARCHAR", "text", "Loan ID"], ["seller", "VARCHAR", "text", "Seller"],
  ["program", "VARCHAR", "text", "Program"], ["product", "VARCHAR", "text", "Product"],
  ["note_rate", "DOUBLE", "number", "Note Rate (%)"], ["current_upb", "DECIMAL(14,2)", "number", "Current UPB ($)"],
  ["fico", "INTEGER", "number", "FICO"], ["ltv", "DOUBLE", "number", "LTV (%)"],
  ["dti", "DOUBLE", "number", "DTI (%)"], ["state", "VARCHAR", "text", "State"],
  ["occupancy", "VARCHAR", "text", "Occupancy"], ["dq_status", "VARCHAR", "text", "DQ Status"],
].map(([name, type, kind, label]) => ({ name, type, kind, label, default_visible: true }));
const COLUMNS = new Map(INFO.map((c) => [c.name, c]));

// BUSINESS: "the largest NY loan" as the server stores it: the agent selected
//   loan_id, current_upb and a computed "age"; the other ten were added.
const STORED: StoredQuery = {
  query_id: "q_1", title: "Largest NY loans", sql: "SELECT loan_id, current_upb, loan_age AS age FROM loans",
  columns: [...INFO.map((c) => c.name), "age"],
  rows: [["LN00000001", "Seller A", "Conventional", "30Y Fixed", 6.125, 812345.67, 742, 80, 36.5,
          "NY", "Primary", "Current", 14]],
  row_count: 1, total_rows: 1, truncated: false, loan_tape: null,
  added_columns: ["seller", "program", "product", "note_rate", "fico", "ltv", "dti", "state", "occupancy", "dq_status"],
};

describe("QueryResultTable with the default columns (Step 4c)", () => {
  it("shows every default column, then the agent's own, with tape labels and formats", () => {
    render(<MemoryRouter><QueryResultTable queryId="q_1" initial={STORED} columns={COLUMNS} onOpenLoan={vi.fn()} /></MemoryRouter>);
    const table = screen.getByRole("table");
    // BUSINESS: same left-to-right order as the stored result: loan ID first, the
    //   agent's computed "age" last, under its own name.
    const headers = within(table).getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toEqual([...INFO.map((c) => c.label), "age"]);
    // BUSINESS: the added fields use the Loan Tape's formats: rate to 3 decimals,
    //   money in whole dollars with commas, numbers right-aligned so digits line up.
    expect(within(table).getByText("6.125")).toHaveClass("num");
    expect(within(table).getByText("812,346")).toHaveClass("num");
    expect(within(table).getByText("Seller A")).not.toHaveClass("num");
    // BUSINESS: the loan ID still opens the loan drawer.
    expect(within(table).getByRole("button", { name: "LN00000001" })).toBeInTheDocument();
  });
});
