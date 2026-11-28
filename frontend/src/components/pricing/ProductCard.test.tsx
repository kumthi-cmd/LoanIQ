/**
 * Tests for components/pricing/ProductCard.tsx and PriceFileStrip.tsx.
 * BUSINESS: a product card must say where its current coupon comes from (Treasury
 *   plus a spread) and when its Current month rolls (SIFMA's dates, the days to the
 *   next settlement, the financing rate); the strip must say which trade date and
 *   curve the prices are for, flag a stale curve, and link the public sources.
 * TECH: React Testing Library on the hand-written fixture (pricing/priceGridFixture.ts).
 */
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PRICE_GRID, UMBS30 } from "../../pricing/priceGridFixture";
import { PriceFileStrip } from "./PriceFileStrip";
import { ProductCard } from "./ProductCard";

describe("ProductCard", () => {
  it("shows the current coupon, its anchor and the SIFMA roll", () => {
    render(<ProductCard product={UMBS30} />);
    const card = within(screen.getByRole("article", { name: "UMBS 30" }));
    // BUSINESS: rates with three decimals: 10Y 4.940 + 1.350 = 6.290%.
    expect(card.getByText("6.290%")).toBeInTheDocument();
    expect(card.getByText("10Y 4.940 + 1.350 spread")).toBeInTheDocument();
    expect(card.getByText("Class A")).toBeInTheDocument();
    expect(card.getByText("Dec 2026")).toBeInTheDocument();
    expect(card.getByText("Notify 08 Dec")).toBeInTheDocument();
    expect(card.getByText("Settle 10 Dec")).toBeInTheDocument();
    expect(card.getByText("Rolls to Jan 2027 · 35 days")).toBeInTheDocument();
    expect(card.getByText("Financing rate 4.270%")).toBeInTheDocument();
  });

  it("explains its terms from the glossary", () => {
    render(<ProductCard product={UMBS30} />);
    expect(screen.getByText("Current coupon")).toHaveAttribute("title", expect.stringMatching(/trade at par/));
    expect(screen.getByText("Class A")).toHaveAttribute("title", expect.stringMatching(/settlement dates/));
  });

  // TECH: no months (a malformed row) still draws the current coupon.
  it("draws a product with no months without the roll", () => {
    render(<ProductCard product={{ ...UMBS30, months: [] }} />);
    expect(screen.getByText("6.290%")).toBeInTheDocument();
    expect(screen.queryByText(/Notify/)).not.toBeInTheDocument();
  });
});

describe("PriceFileStrip", () => {
  it("shows the trade date, a live curve, the source and the public data links", () => {
    render(<PriceFileStrip grid={PRICE_GRID} />);
    expect(screen.getAllByText("Fri 27 Nov 2026")).toHaveLength(2);
    expect(screen.getByText("Live").closest(".status-pill")).toHaveClass("status-live");
    expect(screen.getByText("LoanIQ illustrative model")).toBeInTheDocument();
    // BUSINESS: the model has no url, so only Treasury and SIFMA are links.
    const links = screen.getAllByRole("link");
    expect(links.map((a) => a.getAttribute("href"))).toEqual([
      "https://home.treasury.gov/treasury-daily-interest-rate-xml-feed",
      "https://www.sifma.org/resources/general/mbs-notification-and-settlement-dates/",
    ]);
  });

  // BUSINESS: a curve that is not today's is a warning, not a quiet detail.
  it.each([["cached", "Cached"], ["fixture", "Sample curve"]] as const)("flags a %s curve", (status, label) => {
    render(<PriceFileStrip grid={{ ...PRICE_GRID, curve_status: status }} />);
    expect(screen.getByText(label).closest(".status-pill")).toHaveClass(`status-${status}`);
  });
});
