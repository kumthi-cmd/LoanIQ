/**
 * Tests for App.tsx with its header, sidebar and Loan Tape screen together.
 * BUSINESS: a visitor opening LoanIQ sees the synthetic-data warning, the whole
 *   workflow in the sidebar (only Loan Tape live, the rest marked Planned), the
 *   tape's headline numbers and panels from the API, desk-question chips that filter
 *   the grid, the explanation open beside it, and a header count that follows the
 *   grid's filter.
 * TECH: createMemoryRouter runs the real routes without a browser URL bar. fetch is
 *   mocked per URL. LoanGrid is replaced by a stub (vi.mock) because AG Grid needs
 *   real layout that jsdom does not have; the real grid is covered by Playwright (e2e/).
 */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RouterProvider, createMemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { routes } from "./App";

// TECH: the stub shows what the screen passed it (desk question, hidden columns) and
//   reports a filtered count when its button is clicked, like the real grid does
//   when a block arrives.
vi.mock("./components/LoanGrid", () => ({
  LoanGrid: ({ columns, onRowCount, question, hiddenColumns }: {
    columns: unknown[];
    onRowCount: (n: number) => void;
    question: string | null;
    hiddenColumns: ReadonlySet<string>;
  }) => (
    <div>
      <span>grid with {columns.length} columns</span>
      <span>grid question: {question ?? "none"}</span>
      <span>grid hidden: {[...hiddenColumns].join(",") || "none"}</span>
      <button onClick={() => onRowCount(1234)}>apply filter</button>
      <button onClick={() => onRowCount(1)}>narrow filter</button>
    </div>
  ),
}));

const SUMMARY = { loan_count: 2000, total_current_upb: 6.4e8, wac: 6.4, wa_fico: 742, wa_ltv: 78, delinquent_loans: 61 };
const COLUMNS = [
  { name: "loan_id", type: "VARCHAR", kind: "text", label: "Loan ID" },
  { name: "state", type: "VARCHAR", kind: "text", label: "State" },
  { name: "servicer", type: "VARCHAR", kind: "text", label: "Servicer" },
];
const BREAKDOWNS = {
  programs: [{ program: "Conventional", loans: 1014, current_upb: 212_804_314.92 }],
  note_rates: [
    { low: null, high: 2.5, loans: 3, current_upb: 1e6 },
    { low: 2.5, high: null, loans: 7, current_upb: 3e6 },
  ],
  dq_status: [
    { status: "Current", loans: 1848, current_upb: 6e8 },
    { status: "30", loans: 65, current_upb: 2e7 },
  ],
};
const QUESTIONS = [{ id: "ltv_over_125", loans: 20, current_upb: 3.4e6 }];
const TAPE = { loans: 2000, fields: 41, sellers: 6 };

// TECH: the mock answers by URL, like the real API; anything else is a 404.
function answer(url: string): unknown {
  if (url.includes("/api/loans/summary")) return SUMMARY;
  if (url.includes("/api/loans/columns")) return COLUMNS;
  if (url.includes("/api/loans/breakdowns")) return BREAKDOWNS;
  if (url.includes("/api/loans/questions")) return QUESTIONS;
  if (url.includes("/api/tape")) return TAPE;
  return undefined;
}

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const body = answer(url);
      return Promise.resolve({ ok: body !== undefined, status: body === undefined ? 404 : 200,
        statusText: "", json: () => Promise.resolve(body ?? { detail: "not found" }) });
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

const renderApp = () => render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ["/"] })} />);

describe("App", () => {
  it("shows the LoanIQ Labs logo, what it is and the synthetic data badge", async () => {
    renderApp();
    // BUSINESS: the brand is the page's one top heading, read out as "LoanIQ Labs".
    // TECH: the heading's name comes from the logo image's alt text, so both must
    //   match, and the image must be the 48 px dark-background header logo from brand/.
    const heading = screen.getByRole("heading", { level: 1, name: "LoanIQ Labs" });
    const logo = within(heading).getByRole("img", { name: "LoanIQ Labs" });
    expect(logo).toHaveAttribute("src", expect.stringContaining("loaniq-labs_horizontal_dark-bg_48px"));
    expect(logo).toHaveAttribute("height", "48");
    expect(screen.getByText("Mortgage capital markets desk")).toBeInTheDocument();
    expect(screen.getByText("Synthetic data · demonstration only")).toBeInTheDocument();
  });

  it("lists the workflow in groups, with only Loan Tape live and the rest Planned", () => {
    renderApp();
    const nav = within(screen.getByRole("navigation", { name: "Screens" }));
    expect(nav.getByRole("link", { name: "Loan Tape" })).toHaveAttribute("aria-current", "page");
    // BUSINESS: the one other link is the repo in the footer, not a screen.
    expect(nav.getAllByRole("link").map((a) => a.textContent)).toEqual(["1Loan Tape", "kumthi-cmd/LoanIQ"]);
    const slotting = nav.getByText("Slotting").closest("[aria-disabled]");
    expect(slotting).toHaveAttribute("aria-disabled", "true");
    expect(slotting).toHaveTextContent(/^5Slotting\s*Planned$/);
    for (const group of ["Tape", "Price", "Trade", "Showcase"]) {
      expect(nav.getByRole("list", { name: group })).toBeInTheDocument();
    }
  });

  it("shows the Ask the tape box disabled and marked Planned", () => {
    renderApp();
    const box = screen.getByRole("searchbox", { name: /Ask the tape/ });
    expect(box).toBeDisabled();
  });

  it("loads the tiles, the panels, the chips, the tape line and the grid from the API", async () => {
    renderApp();
    expect(await screen.findByText("2,000")).toBeInTheDocument();
    expect(await screen.findByText("Seller tape · 41 fields · 6 fictional sellers")).toBeInTheDocument();
    const mix = within(screen.getByRole("region", { name: "Program mix" }));
    expect(await mix.findByText("212.8")).toBeInTheDocument();
    const dq = within(screen.getByRole("region", { name: "MBA delinquency" }));
    expect(dq.getByText("1,848")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /LTV over 125\s*20/ })).toHaveAttribute("aria-pressed", "false");
    expect(await screen.findByText("grid with 3 columns")).toBeInTheDocument();
  });

  it("opens the grid on the default columns and hides the rest", async () => {
    // BUSINESS: servicer is not one of the fields a trader reads first.
    renderApp();
    expect(await screen.findByText("grid hidden: servicer")).toBeInTheDocument();
  });

  it("filters the grid by a desk question, and clears it on a second click", async () => {
    renderApp();
    const chip = await screen.findByRole("button", { name: /LTV over 125/ });
    expect(await screen.findByText("grid question: none")).toBeInTheDocument();
    await userEvent.click(chip);
    expect(chip).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("grid question: ltv_over_125")).toBeInTheDocument();
    await userEvent.click(chip);
    expect(chip).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByText("grid question: none")).toBeInTheDocument();
  });

  it("shows the explanation open by default, and hides and reopens it", async () => {
    renderApp();
    const toggle = screen.getByRole("button", { name: "Hide explanation" });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("complementary", { name: "Screen explanation" })).toBeInTheDocument();
    await userEvent.click(toggle);
    expect(screen.queryByRole("complementary", { name: "Screen explanation" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Explain this screen" }));
    expect(screen.getByRole("complementary", { name: "Screen explanation" })).toBeInTheDocument();
  });

  it("shows Export CSV disabled and marked Planned", () => {
    renderApp();
    expect(screen.getByRole("button", { name: /Export CSV/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Export CSV/ })).toHaveTextContent("Planned");
  });

  it("shows the grid's matching row count in the header and the grid footer", async () => {
    renderApp();
    const count = screen.getByTestId("row-count");
    expect(count).toHaveTextContent("… loans");
    await userEvent.click(await screen.findByRole("button", { name: "apply filter" }));
    expect(count).toHaveTextContent("1,234 loans");
    expect(screen.getByTestId("grid-showing")).toHaveTextContent(/^1,234 of 2,000 loans · server-paged, 100 loans/);
    await userEvent.click(screen.getByRole("button", { name: "narrow filter" }));
    // BUSINESS: one loan reads "1 loan", not "1 loans". TECH: exact match, not substring.
    expect(count).toHaveTextContent(/^1 loan$/);
  });

  it("shows a not-found screen inside the app for an unknown URL", () => {
    // BUSINESS: an old or mistyped link is never a dead end.
    render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ["/no/such/screen"] })} />);
    expect(screen.getByRole("heading", { name: "Screen not found" })).toBeInTheDocument();
    expect(screen.getByText("Synthetic data · demonstration only")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to the Loan Tape" })).toHaveAttribute("href", "/");
  });

  it("says so when the API cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("Failed to fetch"))));
    renderApp();
    expect((await screen.findAllByRole("alert"))[0]).toHaveTextContent("Could not reach the loan API");
  });
});
