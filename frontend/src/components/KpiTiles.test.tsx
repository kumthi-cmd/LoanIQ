/**
 * Tests for components/KpiTiles.tsx.
 * BUSINESS: the headline numbers a trader quotes must show with the right units and
 *   precision: dollars with commas, WAC to 3 decimals, FICO in whole points, LTV to
 *   2 decimals, and a dash (not 0) when an average does not exist.
 */
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Summary } from "../api/types";
import { KpiTiles } from "./KpiTiles";

const SUMMARY: Summary = {
  loan_count: 2000,
  total_current_upb: 640123456.78,
  wac: 6.412,
  wa_fico: 742.35,
  wa_ltv: 78.1,
  delinquent_loans: 61,
};

const tile = (name: string) => within(screen.getByRole("region", { name }));

describe("KpiTiles", () => {
  it("shows all six headline numbers with units", () => {
    render(<KpiTiles summary={SUMMARY} />);
    expect(tile("Loans").getByText("2,000")).toBeInTheDocument();
    expect(tile("Current UPB").getByText("$640,123,457")).toBeInTheDocument();
    expect(tile("WAC").getByText("6.412%")).toBeInTheDocument();
    expect(tile("WA FICO").getByText("742")).toBeInTheDocument();
    expect(tile("WA LTV").getByText("78.10%")).toBeInTheDocument();
    expect(tile("Delinquent loans").getByText("61")).toBeInTheDocument();
  });

  it("shows a dash, not zero, for averages of an empty tape", () => {
    render(<KpiTiles summary={{ ...SUMMARY, loan_count: 0, total_current_upb: 0, wac: null, wa_fico: null, wa_ltv: null, delinquent_loans: 0 }} />);
    expect(tile("WAC").getByText("—")).toBeInTheDocument();
    expect(tile("WA LTV").getByText("—")).toBeInTheDocument();
  });

  it("shows a loading marker before the summary arrives", () => {
    render(<KpiTiles summary={null} />);
    expect(screen.getAllByText("…")).toHaveLength(6);
  });

  it("explains each label from the glossary and says it covers the whole tape", () => {
    render(<KpiTiles summary={SUMMARY} />);
    expect(tile("WAC").getByText("WAC")).toHaveAttribute("title", expect.stringMatching(/Weighted-average coupon/));
    expect(screen.getByText(/Whole tape/)).toBeInTheDocument();
  });
});
