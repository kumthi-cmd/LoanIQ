/**
 * Tests for the small parts of the Ask the Tape screen: tool chip labels and the
 * Offline banner's rule.
 *
 * BUSINESS: a refused call must look refused, a looked-up term must say which term,
 *   and the Offline banner must show only while built-in rules answer for a lasting
 *   reason (no key, a daily limit), not after a one-off timeout.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ToolStep } from "../../ask/conversation";
import { isOffline, OfflineBanner } from "./OfflineBanner";
import { chipDetail, chipLabel } from "./ToolChips";

const step = (name: string, input: Record<string, unknown>, result?: Partial<ToolStep["result"]>): ToolStep => ({
  id: "c1", name, input, result: result ? { id: "c1", name, status: "ok", ...result } as ToolStep["result"] : undefined,
});

describe("chipLabel and chipDetail", () => {
  it("names what each tool did", () => {
    expect(chipLabel(step("query_tape", {}, { total_rows: 1234 }))).toBe("query_tape → 1,234 rows");
    expect(chipLabel(step("query_tape", {}, { total_rows: 1 }))).toBe("query_tape → 1 row");
    expect(chipLabel(step("lookup_term", { term: "MBA delinquency" }, {}))).toBe("lookup_term: MBA delinquency");
    expect(chipLabel(step("get_loan", { loan_id: "ln1" }, { loan_id: "LN00000001" }))).toBe("get_loan: LN00000001");
    expect(chipLabel(step("summarize_tape", {}))).toBe("summarize_tape …");
    expect(chipLabel(step("query_tape", {}, { status: "rejected" }))).toBe("query_tape ✕ refused");
  });

  it("shows the SQL that ran, the SQL a refused call tried, or the input", () => {
    expect(chipDetail(step("query_tape", { sql: "model's" }, { sql: "checked" }))).toBe("checked");
    expect(chipDetail(step("query_tape", { sql: "SELECT * FROM x" }, { status: "rejected" }))).toBe("SELECT * FROM x");
    expect(chipDetail(step("lookup_term", { term: "WAC" }, {}))).toBe("term: WAC");
    expect(chipDetail(step("list_columns", {}, {}))).toBe("(no input)");
  });
});

// TECH: since Step 5c the status also carries the desk stages (AgentScopeStrip.test.tsx);
//   the banner ignores them, so these statuses carry none.
describe("OfflineBanner", () => {
  it("shows only for lasting reasons", () => {
    expect(isOffline({ mode: "offline", reason: "daily_budget", notice: "n", stages: [] })).toBe(true);
    expect(isOffline({ mode: "offline", reason: "visitor_limit", notice: "n", stages: [] })).toBe(true);
    expect(isOffline({ mode: "offline", reason: "timeout", notice: "n", stages: [] })).toBe(false);
    expect(isOffline({ mode: "model", reason: null, notice: null, stages: [] })).toBe(false);
    expect(isOffline(null)).toBe(false);
  });

  it("draws nothing while the model answers", () => {
    const { container } = render(<OfflineBanner status={{ mode: "model", reason: null, notice: null, stages: [] }} />);
    expect(container).toBeEmptyDOMElement();
    render(<OfflineBanner status={{ mode: "offline", reason: "daily_budget", notice: "Budget used up.", stages: [] }} />);
    expect(screen.getByRole("status")).toHaveTextContent("Budget used up.");
  });
});
