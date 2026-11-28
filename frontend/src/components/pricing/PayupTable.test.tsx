/**
 * Tests for components/pricing/PayupTable.tsx.
 * BUSINESS: the pay-up table shows the S-curve a desk expects: a story is worth 0 on
 *   a discount coupon and its full pay-up on a premium one, in 32nds ("18+"), for the
 *   product the trader picks; the nearest coupon's column is tinted, zeros are muted.
 * TECH: React Testing Library on the hand-written fixture (pricing/priceGridFixture.ts).
 */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { PRICE_GRID } from "../../pricing/priceGridFixture";
import { PayupTable } from "./PayupTable";

const table = () => screen.getByRole("table", { name: /^Spec pay-ups over TBA · / });
const row = (story: string) => within(screen.getByRole("rowheader", { name: story }).closest("tr")!).getAllByRole("cell");

describe("PayupTable", () => {
  it("shows the chosen product's stories at its traded coupons, in 32nds", () => {
    render(<PayupTable grid={PRICE_GRID} view="traded" product="UMBS 30" onProductChange={() => {}} />);
    const headers = within(table()).getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toEqual(["Story", "Full", "5.5", "6.0", "6.5"]);
    // BUSINESS: LLB 85K on UMBS 30: full 64; 2 at 5.5, 18+ at 6.0, 42 at 6.5.
    expect(row("LLB 85K").map((c) => c.textContent)).toEqual(["64", "2", "18+", "42"]);
    expect(screen.getByText(/UMBS 30, traded coupons 5.5 to 6.5/)).toBeInTheDocument();
  });

  // BUSINESS: the discount end is worth nothing and is muted; the premium end is full.
  it("shows the whole S-curve in the All view, zeros and model-only coupons muted", () => {
    render(<PayupTable grid={PRICE_GRID} view="all" product="UMBS 30" onProductChange={() => {}} />);
    const cells = row("NY");
    expect(cells.map((c) => c.textContent)).toEqual(["12", "0", "0+", "3+", "8", "12"]);
    expect(cells[1]).toHaveClass("model-only");
    expect(screen.getByText(/UMBS 30, all 5 coupons/)).toBeInTheDocument();
  });

  it("mutes a zero inside the traded band and tints the nearest coupon", () => {
    const grid = {
      ...PRICE_GRID,
      payups: [{ ...PRICE_GRID.payups[1], cells: PRICE_GRID.payups[1].cells.map((c) => ({ ...c, payup_32nds: "0.0" })) }],
    };
    render(<PayupTable grid={grid} view="traded" product="UMBS 30" onProductChange={() => {}} />);
    const cells = row("NY");
    expect(cells[1]).toHaveClass("zero");
    expect(cells[3]).toHaveClass("nearest");
    expect(within(table()).getByRole("columnheader", { name: "6.5" })).toHaveClass("nearest");
  });

  it("switches product from the chips", async () => {
    const onProductChange = vi.fn();
    render(<PayupTable grid={PRICE_GRID} view="traded" product="UMBS 30" onProductChange={onProductChange} />);
    const chips = within(screen.getByRole("group", { name: "Product" }));
    expect(chips.getByRole("button", { name: "UMBS 30" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(chips.getByRole("button", { name: "UMBS 15" }));
    expect(onProductChange).toHaveBeenCalledWith("UMBS 15");
  });

  // BUSINESS: UMBS 15's current coupon is lower (5.74), so the same story pays more at 6.0.
  it("shows another product's own pay-ups", () => {
    render(<PayupTable grid={PRICE_GRID} view="traded" product="UMBS 15" onProductChange={() => {}} />);
    expect(row("LLB 85K").map((c) => c.textContent)).toEqual(["64", "20+", "44", "61+"]);
    expect(screen.queryByRole("rowheader", { name: "NY" })).not.toBeInTheDocument();
  });

  // TECH: a stale product name (not in the grid) falls back to the first product.
  it("falls back to the first product for an unknown name", () => {
    render(<PayupTable grid={PRICE_GRID} view="traded" product="GNMA II 30" onProductChange={() => {}} />);
    expect(screen.getByRole("button", { name: "UMBS 30" })).toHaveAttribute("aria-pressed", "true");
  });
});
