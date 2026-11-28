/**
 * Tests for screens/PriceGridScreen.tsx, inside the real layout and routes (Step 6c).
 * BUSINESS: a visitor opening the Price Grid from the sidebar sees:
 *   - the "Illustrative, as of" line, the trade date and the curve's freshness;
 *   - six (here two) product cards, the TBA price table and the pay-up table;
 *   - one coupon switch that changes both tables together, and product chips for
 *     the pay-ups;
 *   - the server's reason, not an empty screen, when no price file can be built (503);
 *   - the explanation and its 13 glossary terms one click away.
 * TECH: createMemoryRouter runs the real routes; fetch is mocked per URL and answers
 *   with the hand-written fixture (pricing/priceGridFixture.ts). Calls the layout
 *   makes (slotting status) get a 404, which the layout already tolerates.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RouterProvider, createMemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { routes } from "../App";
import { PRICE_GRID } from "../pricing/priceGridFixture";

/** TECH: answer /api/prices/grid with `grid` (or an error), anything else with a 404. */
function mockApi(grid: unknown, status = 200) {
  vi.stubGlobal("fetch", vi.fn((url: string) => {
    if (String(url).includes("/api/prices/grid")) {
      return Promise.resolve({ ok: status === 200, status, statusText: "", json: () => Promise.resolve(grid) });
    }
    return Promise.resolve({ ok: false, status: 404, statusText: "", json: () => Promise.resolve({ detail: "not found" }) });
  }));
}
afterEach(() => vi.unstubAllGlobals());

const renderPrices = () =>
  render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: ["/prices"] })} />);

describe("PriceGridScreen", () => {
  it("shows the price file: label, strip, cards, prices and pay-ups", async () => {
    mockApi(PRICE_GRID);
    renderPrices();
    expect(await screen.findByText("Illustrative, as of 2026-11-27")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Price Grid" })).toBeInTheDocument();
    expect(screen.getByLabelText("Price file")).toHaveTextContent("Trade date Fri 27 Nov 2026");
    const cards = within(screen.getByRole("region", { name: "Products" }));
    expect(cards.getAllByRole("article").map((a) => a.getAttribute("aria-labelledby"))).toHaveLength(2);
    expect(screen.getByRole("table", { name: "TBA prices · Current month" })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Spec pay-ups over TBA · UMBS 30" })).toBeInTheDocument();
    // BUSINESS: the sidebar marks the Price Grid as the current page.
    expect(screen.getByRole("link", { name: "Price Grid" })).toHaveAttribute("aria-current", "page");
  });

  it("shows a loading line until the price file arrives", async () => {
    mockApi(PRICE_GRID);
    renderPrices();
    expect(screen.getByRole("status")).toHaveTextContent("Loading today’s price file…");
    await screen.findByText("Illustrative, as of 2026-11-27");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  // BUSINESS: one switch changes both tables, so pay-ups line up with the prices.
  it("switches both tables between traded coupons and all coupons", async () => {
    mockApi(PRICE_GRID);
    renderPrices();
    const prices = await screen.findByRole("table", { name: "TBA prices · Current month" });
    expect(within(prices).queryByRole("rowheader", { name: "2.0" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "All 5" }));
    expect(within(prices).getByRole("rowheader", { name: "2.0" })).toBeInTheDocument();
    const payups = screen.getByRole("table", { name: "Spec pay-ups over TBA · UMBS 30" });
    expect(within(payups).getByRole("columnheader", { name: "2.0" })).toBeInTheDocument();
  });

  it("shows another product's pay-ups from the chips", async () => {
    mockApi(PRICE_GRID);
    renderPrices();
    await screen.findByText("Illustrative, as of 2026-11-27");
    await userEvent.click(within(screen.getByRole("group", { name: "Product" })).getByRole("button", { name: "UMBS 15" }));
    expect(screen.getByRole("table", { name: "Spec pay-ups over TBA · UMBS 15" })).toBeInTheDocument();
  });

  // BUSINESS: past the end of SIFMA's calendar the API refuses (503); the desk sees why.
  it("shows the server's reason when no price file can be built", async () => {
    mockApi({ detail: "SIFMA's settlement calendar has no dates after Dec 2027" }, 503);
    renderPrices();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Prices are not available: SIFMA's settlement calendar has no dates after Dec 2027");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("opens the explanation with the Price Grid's terms", async () => {
    mockApi(PRICE_GRID);
    renderPrices();
    await screen.findByText("Illustrative, as of 2026-11-27");
    const button = screen.getByRole("button", { name: "Explain this screen" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(button);
    const panel = within(screen.getByRole("complementary", { name: "Screen explanation" }));
    expect(panel.getByText(/This is the desk's price file/)).toBeInTheDocument();
    expect(panel.getByText("Glossary · Current coupon")).toBeInTheDocument();
    // BUSINESS: the 13 terms the screen depends on (content/screens/price-grid.json).
    expect(within(panel.getByRole("group", { name: "Glossary terms" })).getAllByRole("button")).toHaveLength(13);
    await userEvent.click(panel.getByRole("button", { name: "Drop" }));
    expect(panel.getByText("Glossary · Drop")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Hide explanation" }));
    await waitFor(() => expect(screen.queryByRole("complementary", { name: "Screen explanation" })).not.toBeInTheDocument());
  });
});
