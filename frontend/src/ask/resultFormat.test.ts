/**
 * Tests for ask/resultFormat.ts: answer tables formatted like the Loan Tape.
 *
 * BUSINESS: protects the desk's reading of numbers: money with commas, rates with 3
 *   decimals, LTV with 2 (.claude/rules/frontend.md), and every loan ID in an answer
 *   opening that loan.
 */
import { describe, expect, it } from "vitest";
import type { ColumnInfo } from "../api/types";
import { columnLabel, formatCell, isNumericColumn, linkLoanIds, loanIdFromHref } from "./resultFormat";

const COLS = new Map<string, ColumnInfo>([
  ["current_upb", { name: "current_upb", type: "DECIMAL(14,2)", kind: "number", label: "Current UPB ($)", default_visible: false }],
  ["note_rate", { name: "note_rate", type: "DECIMAL(6,3)", kind: "number", label: "Note Rate (%)", default_visible: false }],
  ["ltv", { name: "ltv", type: "DECIMAL(6,2)", kind: "number", label: "LTV (%)", default_visible: false }],
  ["orig_date", { name: "orig_date", type: "DATE", kind: "date", label: "Origination date", default_visible: false }],
  ["modified", { name: "modified", type: "BOOLEAN", kind: "boolean", label: "Modified", default_visible: false }],
]);

describe("formatCell", () => {
  it("uses the tape's formats for tape columns", () => {
    expect(formatCell("current_upb", 1910592.4, COLS)).toBe("1,910,592");
    expect(formatCell("note_rate", 4.5, COLS)).toBe("4.500");
    expect(formatCell("ltv", 92.1, COLS)).toBe("92.10");
    expect(formatCell("orig_date", "2024-03-01", COLS)).toBe("2024-03-01");
    expect(formatCell("modified", true, COLS)).toBe("Yes");
  });

  it("shows computed columns plainly, up to 3 decimals, and blanks for null", () => {
    expect(formatCell("wac", 4.28216, COLS)).toBe("4.282");
    expect(formatCell("loans", 1234, COLS)).toBe("1,234");
    expect(formatCell("seller", "Alder & Finch", COLS)).toBe("Alder & Finch");
    expect(formatCell("ltv", null, COLS)).toBe("");
  });

  it("labels and aligns columns", () => {
    expect(columnLabel("ltv", COLS)).toBe("LTV (%)");
    expect(columnLabel("wac", COLS)).toBe("wac");
    expect(isNumericColumn("wac", COLS, 4.2)).toBe(true);
    expect(isNumericColumn("seller", COLS, "x")).toBe(false);
  });
});

describe("loan IDs in answers", () => {
  it("links every loan ID and reads it back from the link", () => {
    expect(linkLoanIds("LN72972382 and LN90652944, not LN123")).toBe(
      "[LN72972382](#loan-LN72972382) and [LN90652944](#loan-LN90652944), not LN123");
    expect(loanIdFromHref("#loan-LN72972382")).toBe("LN72972382");
    expect(loanIdFromHref("https://example.com")).toBeNull();
    expect(loanIdFromHref(undefined)).toBeNull();
  });
});
