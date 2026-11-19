/**
 * Tests for content/content.ts and the content files it reads.
 * BUSINESS: one fact in one place. Every term a screen points to must exist in
 *   content/glossary.json, and every screen explanation must have its Business and
 *   Technical sections (.claude/rules/showcase.md).
 */
import { describe, expect, it } from "vitest";
import { TILES } from "../components/KpiTiles";
import { columnTerms, glossary, lookupTerm, screenExplanations, termTooltip } from "./content";

describe("glossary", () => {
  it("defines each term once, with a definition and why it matters", () => {
    const terms = glossary.map((g) => g.term);
    expect(new Set(terms).size).toBe(terms.length);
    for (const g of glossary) {
      expect(g.definition.length).toBeGreaterThan(0);
      expect(g.why.length).toBeGreaterThan(0);
    }
  });

  it("has every term the grid headers point to", () => {
    for (const [column, term] of Object.entries(columnTerms)) {
      expect(lookupTerm(term), `${column} -> ${term}`).toBeDefined();
    }
  });

  it("has every term the KPI tiles point to", () => {
    for (const tile of TILES) expect(lookupTerm(tile.term), tile.label).toBeDefined();
  });

  it("builds tooltips from definition and why", () => {
    expect(termTooltip("WAC")).toMatch(/^Weighted-average coupon.*Why it matters: /);
    expect(termTooltip("not a term")).toBeUndefined();
  });
});

describe("screen explanations", () => {
  it.each(Object.entries(screenExplanations))("%s has Business and Technical sections", (_id, md) => {
    expect(md).toMatch(/^## Business$/m);
    expect(md).toMatch(/^## Technical$/m);
  });
});
