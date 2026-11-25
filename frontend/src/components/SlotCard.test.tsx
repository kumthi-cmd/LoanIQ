/**
 * Tests for components/SlotCard.tsx, the loan hover card, and the slot grid cells.
 *
 * BUSINESS: protects what a trader reads on hover: for LN78265415 (the board's loan)
 *   UMBS 30Y at 2.5 down / 3.0 up, three spec stories each with its rule and why, and
 *   the generic TBA slot; for an ARM, "Not slotted" and the reason. The same loan
 *   hovered twice asks the server once. In the grid, stories are pills and "Generic
 *   TBA", the not-slotted reasons and "Not slotted" are quiet text.
 * TECH: fetch is mocked per URL; the cells are rendered with the props AG Grid would
 *   pass (only value matters to them).
 */
import { render, screen, within } from "@testing-library/react";
import type { CustomCellRendererProps } from "ag-grid-react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { LoanRow, LoanSlots } from "../api/types";
import { SlotCell } from "../grid/SlotCell";
import { isStoryList, SpecStoriesCell } from "../grid/SpecStoriesCell";
import { ARM_CARD, BOARD_CARD, RUN } from "../slotting/slottingFixtures";
import { cardPlacement, SlotCard } from "./SlotCard";

const ANCHOR = new DOMRect(100, 200, 90, 30);
const cards: Record<string, LoanSlots> = { [BOARD_CARD.loan_id]: BOARD_CARD, [ARM_CARD.loan_id]: ARM_CARD };

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn((url: string) => {
    const id = /\/api\/loans\/(\w+)\/slots/.exec(String(url))?.[1] ?? "";
    const card = cards[id];
    return Promise.resolve(new Response(JSON.stringify(card ?? { detail: "No loan" }), { status: card ? 200 : 404 }));
  }));
});
afterEach(() => vi.unstubAllGlobals());

describe("SlotCard", () => {
  it("shows the board loan's coupons, its three stories with rule and why, and generic TBA", async () => {
    render(<SlotCard loanId="LN78265415" anchor={ANCHOR} runAt={RUN.run_at!} />);
    const card = await screen.findByRole("tooltip");
    expect(await within(card).findByText("Slotted")).toBeInTheDocument();
    expect(within(card).getByText("UMBS 30Y")).toBeInTheDocument();
    expect(within(card).getByText("2.5")).toBeInTheDocument();
    expect(within(card).getByText("3.0")).toBeInTheDocument();
    expect(within(card).getByText("Where it can go · 3 spec stories")).toBeInTheDocument();
    expect(within(card).getByText("LLB 275K spec")).toBeInTheDocument();
    expect(within(card).getByText("orig_upb <= 275000")).toBeInTheDocument();
    expect(within(card).getByText(/fits the \$275K tier, the lowest it fits/)).toBeInTheDocument();
    expect(within(card).getByText("Generic TBA · UMBS 30Y 2.5")).toBeInTheDocument();
    expect(within(card).getByText("$268,800")).toBeInTheDocument(); // TECH: the app's money format, whole dollars
    expect(within(card).getByText("3.125%")).toBeInTheDocument();
  });

  it("says why a loan is not slotted", async () => {
    render(<SlotCard loanId="LN79962194" anchor={ANCHOR} runAt={RUN.run_at!} />);
    const card = await screen.findByRole("tooltip");
    expect(await within(card).findByText(/has no fixed-rate TBA coupon/)).toBeInTheDocument();
    expect(within(card).getAllByText("Not slotted").length).toBeGreaterThan(0);
    expect(within(card).queryByText(/Generic TBA/)).toBeNull();
  });

  it("asks the server once per loan and run", async () => {
    const runAt = "2026-11-25T17:00:00Z";
    const { unmount } = render(<SlotCard loanId="LN78265415" anchor={ANCHOR} runAt={runAt} />);
    await screen.findByText("UMBS 30Y");
    unmount();
    render(<SlotCard loanId="LN78265415" anchor={ANCHOR} runAt={runAt} />);
    expect(screen.getByText("UMBS 30Y")).toBeInTheDocument();
    const calls = vi.mocked(fetch).mock.calls.length;
    expect(calls).toBe(1);
  });

  it("shows the server's message when the card cannot load", async () => {
    render(<SlotCard loanId="LN00000000" anchor={ANCHOR} runAt={RUN.run_at!} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("No loan");
  });

  it("sits right of the cell, or left of it near the window's right edge", () => {
    expect(cardPlacement(ANCHOR, 1440, 900).left).toBe(ANCHOR.right + 8);
    expect(cardPlacement(new DOMRect(1300, 200, 90, 30), 1440, 900).left).toBe(1300 - 380 - 8);
    expect(cardPlacement(new DOMRect(100, 850, 90, 30), 1440, 900).top).toBeLessThan(850);
  });
});

const cellProps = (value: string | null) => ({ value }) as CustomCellRendererProps<LoanRow, string | null>;

describe("slot grid cells", () => {
  it("draws each story as a pill", () => {
    const { container } = render(<SpecStoriesCell {...cellProps("LLB 275K, NY, Low FICO")} />);
    expect([...container.querySelectorAll(".story-pill")].map((p) => p.textContent)).toEqual(["LLB 275K", "NY", "Low FICO"]);
  });

  it("shows generic TBA and not-slotted reasons as quiet text, not pills", () => {
    for (const text of ["Generic TBA", "Delinquent", "No agency pool", "No TBA product"]) {
      expect(isStoryList(text)).toBe(false);
    }
    const { container } = render(<SpecStoriesCell {...cellProps("Generic TBA")} />);
    expect(container.querySelector(".story-pill")).toBeNull();
    expect(container.querySelector(".muted")).toHaveTextContent("Generic TBA");
  });

  it("greys a Not slotted slot and leaves a real slot as is", () => {
    const { container, rerender } = render(<SlotCell {...cellProps("Not slotted")} />);
    expect(container.querySelector(".muted")).toHaveTextContent("Not slotted");
    rerender(<SlotCell {...cellProps("UMBS 30Y 2.5 / 3.0")} />);
    expect(container.querySelector(".muted")).toBeNull();
    expect(container).toHaveTextContent("UMBS 30Y 2.5 / 3.0");
  });
});
