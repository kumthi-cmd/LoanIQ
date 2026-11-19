/**
 * Tests for App.tsx with its header, sidebar and Loan Tape screen together.
 * BUSINESS: a visitor opening LoanIQ sees the synthetic-data warning, the whole
 *   workflow in the sidebar (later screens marked with their step), the tape's
 *   headline numbers, and a header count that follows the grid's filter.
 * TECH: createMemoryRouter runs the real routes without a browser URL bar. fetch is
 *   mocked. LoanGrid is replaced by a stub (vi.mock) because AG Grid needs real
 *   layout that jsdom does not have; the real grid is covered by Playwright (e2e/).
 */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RouterProvider, createMemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { routes } from "./App";

// TECH: the stub reports a filtered count when its button is clicked, like the real
//   grid does when a block arrives.
vi.mock("./components/LoanGrid", () => ({
  LoanGrid: ({ columns, onRowCount }: { columns: unknown[]; onRowCount: (n: number) => void }) => (
    <div>
      <span>grid with {columns.length} columns</span>
      <button onClick={() => onRowCount(1234)}>apply filter</button>
      <button onClick={() => onRowCount(1)}>narrow filter</button>
    </div>
  ),
}));

const SUMMARY = { loan_count: 2000, total_current_upb: 6.4e8, wac: 6.4, wa_fico: 742, wa_ltv: 78, delinquent_loans: 61 };
const COLUMNS = [{ name: "loan_id", type: "VARCHAR", kind: "text", label: "Loan ID" }];

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(url.includes("summary") ? SUMMARY : COLUMNS),
      }),
    ),
  );
});
afterEach(() => vi.unstubAllGlobals());

const renderApp = () => render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ["/"] })} />);

describe("App", () => {
  it("shows the name and the synthetic data badge", async () => {
    renderApp();
    expect(screen.getByRole("heading", { name: "LoanIQ" })).toBeInTheDocument();
    expect(screen.getByText("Synthetic data - demonstration only")).toBeInTheDocument();
  });

  it("lists the workflow in the sidebar, with only Loan Tape live", () => {
    renderApp();
    const nav = within(screen.getByRole("navigation", { name: "Screens" }));
    expect(nav.getByRole("link", { name: "Loan Tape" })).toHaveAttribute("aria-current", "page");
    expect(nav.getAllByRole("link")).toHaveLength(1);
    expect(nav.getByText("Slotting")).toHaveAttribute("aria-disabled", "true");
    expect(nav.getByText("Slotting")).toHaveTextContent("Step 5");
  });

  it("loads the KPI tiles and the grid columns from the API", async () => {
    renderApp();
    expect(await screen.findByText("2,000")).toBeInTheDocument();
    expect(await screen.findByText("grid with 1 columns")).toBeInTheDocument();
  });

  it("shows the grid's matching row count in the header", async () => {
    renderApp();
    const count = screen.getByTestId("row-count");
    expect(count).toHaveTextContent("… loans");
    await userEvent.click(await screen.findByRole("button", { name: "apply filter" }));
    expect(count).toHaveTextContent("1,234 loans");
    await userEvent.click(screen.getByRole("button", { name: "narrow filter" }));
    // BUSINESS: one loan reads "1 loan", not "1 loans". TECH: exact match, not substring.
    expect(count).toHaveTextContent(/^1 loan$/);
  });

  it("shows a not-found screen inside the app for an unknown URL", () => {
    // BUSINESS: an old or mistyped link is never a dead end.
    render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ["/no/such/screen"] })} />);
    expect(screen.getByRole("heading", { name: "Screen not found" })).toBeInTheDocument();
    expect(screen.getByText("Synthetic data - demonstration only")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to the Loan Tape" })).toHaveAttribute("href", "/");
  });

  it("says so when the API cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("Failed to fetch"))));
    renderApp();
    expect((await screen.findAllByRole("alert"))[0]).toHaveTextContent("Could not reach the loan API");
  });
});
