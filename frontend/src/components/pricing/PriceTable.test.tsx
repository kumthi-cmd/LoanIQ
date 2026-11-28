/**
 * Tests for components/pricing/PriceTable.tsx.
 * BUSINESS: the price table a trader reads must show:
 *   - every product's Current price and drop in 32nds, under real column headers;
 *   - the decimal behind each price on hover (98-08+ = 98.265625);
 *   - the coupon nearest each current coupon highlighted, and said out loud;
 *   - model-only coupons muted, and only in the "All" view;
 *   - a negative drop with its minus sign.
 * TECH: React Testing Library on the hand-written fixture (pricing/priceGridFixture.ts).
 */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { PRICE_GRID } from "../../pricing/priceGridFixture";
import { PriceTable } from "./PriceTable";

const table = () => screen.getByRole("table", { name: "TBA prices · Current month" });
/** TECH: the body row for one coupon, found by its row header. */
const row = (coupon: string) => screen.getByRole("rowheader", { name: coupon }).closest("tr")!;

describe("PriceTable", () => {
  it("heads each product with a Price and Drop pair", () => {
    render(<PriceTable grid={PRICE_GRID} view="traded" onViewChange={() => {}} />);
    const t = within(table());
    expect(t.getByRole("columnheader", { name: "UMBS 30" })).toHaveAttribute("colspan", "2");
    expect(t.getAllByRole("columnheader", { name: "Price" })).toHaveLength(2);
    expect(t.getAllByRole("columnheader", { name: "Drop" })).toHaveLength(2);
  });

  // BUSINESS: the traded view hides 2.0 and 8.5, which only the model prices.
  it("shows the traded coupons with prices and drops in 32nds", () => {
    render(<PriceTable grid={PRICE_GRID} view="traded" onViewChange={() => {}} />);
    expect(within(table()).getAllByRole("rowheader").map((h) => h.textContent)).toEqual(["5.5", "6.0", "6.5"]);
    const cells = within(row("6.0")).getAllByRole("cell");
    expect(cells.map((c) => c.firstChild?.textContent)).toEqual(["98-08+", "0-03+", "100-28", "0-02"]);
  });

  it("shows each price's decimal on hover", () => {
    render(<PriceTable grid={PRICE_GRID} view="traded" onViewChange={() => {}} />);
    const price = within(row("6.0")).getAllByRole("cell")[0];
    expect(price).toHaveAttribute("title", "UMBS 30 6.0: 98.265625 points");
  });

  // BUSINESS: UMBS 30 (6.29) is nearest 6.5; UMBS 15 (5.74) is nearest 5.5.
  it("highlights and names the coupon nearest each current coupon", () => {
    render(<PriceTable grid={PRICE_GRID} view="traded" onViewChange={() => {}} />);
    const at65 = within(row("6.5")).getAllByRole("cell");
    expect(at65[0]).toHaveClass("nearest");
    expect(at65[1]).toHaveClass("nearest");
    expect(at65[0]).toHaveTextContent("101-03+ (nearest the current coupon)");
    expect(at65[2]).not.toHaveClass("nearest");
    expect(within(row("5.5")).getAllByRole("cell")[2]).toHaveClass("nearest");
  });

  // BUSINESS: a negative drop keeps its sign; model-only cells are muted and say so.
  it("shows model-only coupons muted, with negative drops signed, in the All view", () => {
    render(<PriceTable grid={PRICE_GRID} view="all" onViewChange={() => {}} />);
    const at20 = within(row("2.0")).getAllByRole("cell");
    expect(at20[0]).toHaveClass("model-only");
    expect(at20[0]).toHaveTextContent("74-08+ (model-only)");
    expect(at20[0]).toHaveAttribute("title", "UMBS 30 2.0: 74.265625 points (model-only)");
    expect(at20[3]).toHaveTextContent("-0-03+");
  });

  it("reports the view switch to the screen", async () => {
    const onViewChange = vi.fn();
    render(<PriceTable grid={PRICE_GRID} view="traded" onViewChange={onViewChange} />);
    const group = within(screen.getByRole("group", { name: "Coupons shown" }));
    expect(group.getByRole("button", { name: "Traded coupons" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(group.getByRole("button", { name: "All 5" }));
    expect(onViewChange).toHaveBeenCalledWith("all");
  });

  it("explains drop, 32nds and model-only from the glossary", () => {
    render(<PriceTable grid={PRICE_GRID} view="traded" onViewChange={() => {}} />);
    expect(screen.getByText("drop")).toHaveAttribute("title", expect.stringMatching(/^The Current price minus/));
    expect(screen.getByText("32nds")).toHaveAttribute("title", expect.stringMatching(/98-08\+ is 98 \+ 8.5\/32/));
    expect(screen.getByText("model-only")).toHaveAttribute("title", expect.stringMatching(/outside the product's traded band/));
  });
});
