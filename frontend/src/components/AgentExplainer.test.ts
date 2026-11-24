/**
 * Tests for popoverPlacement in AgentExplainer.tsx (Step 4d).
 *
 * BUSINESS: the agent explainer always opens fully on screen, next to the mark the
 *   visitor clicked, at a desk monitor's width or a laptop's.
 * TECH: pure numbers in CSS pixels; no DOM needed. DOMRect is built with its
 *   constructor (x, y, width, height), so bottom = y + height.
 */
import { describe, expect, it } from "vitest";
import { popoverPlacement } from "./AgentExplainer";

describe("popoverPlacement", () => {
  it("opens under the mark, left-aligned with it, at most 560 px wide", () => {
    expect(popoverPlacement(new DOMRect(200, 100, 40, 12), 1440, 900))
      .toEqual({ left: 200, top: 120, width: 560, maxHeight: 764 });
  });

  it("never runs past the window's right edge", () => {
    const p = popoverPlacement(new DOMRect(1300, 100, 40, 12), 1440, 900);
    expect(p.left + p.width).toBeLessThanOrEqual(1440 - 16);
  });

  it("fits a narrow window, keeping a 16 px margin each side", () => {
    expect(popoverPlacement(new DOMRect(100, 100, 40, 12), 400, 800))
      .toMatchObject({ left: 16, width: 368 });
  });

  it("starts near the top when the mark is low in the window, so the text has room", () => {
    expect(popoverPlacement(new DOMRect(20, 700, 40, 12), 1440, 900).top).toBe(16);
  });

  it("falls back to the top-left corner without a mark position", () => {
    expect(popoverPlacement(null, 1440, 900)).toMatchObject({ left: 16, top: 24 });
  });
});
