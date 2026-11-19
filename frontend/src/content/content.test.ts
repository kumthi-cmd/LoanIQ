/**
 * Tests for content/content.ts and the content files it reads.
 * BUSINESS: one fact in one place. Every term a screen points to must exist in
 *   content/glossary.json, and every screen explanation must have its Business and
 *   Technical sections (.claude/rules/showcase.md).
 */
import { describe, expect, it } from "vitest";
import { TILES } from "../components/KpiTiles";
import {
  columnTerms, deskQuestionLabels, fillCaption, glossary, lookupTerm, screenExplanations, screenTerms,
  splitExplanation, termTooltip,
} from "./content";

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

  it("has every term the desk-question chips point to", () => {
    for (const q of deskQuestionLabels) expect(lookupTerm(q.term), q.id).toBeDefined();
  });

  it("has every term each Explain panel offers, and the program names the Program mix shows", () => {
    for (const [screen, terms] of Object.entries(screenTerms)) {
      expect(terms.length, screen).toBeGreaterThan(0);
      for (const t of terms) expect(lookupTerm(t), `${screen} -> ${t}`).toBeDefined();
    }
    // BUSINESS: hovering a program in the Program mix panel explains it.
    for (const p of ["Conventional", "High-Balance", "Jumbo", "Non-QM", "FHA", "VA", "USDA", "Note rate"]) {
      expect(lookupTerm(p), p).toBeDefined();
    }
  });

  it("labels each desk question once, with a non-empty label", () => {
    const ids = deskQuestionLabels.map((q) => q.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const q of deskQuestionLabels) expect(q.label.length, q.id).toBeGreaterThan(0);
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
    const { business, technical } = splitExplanation(md);
    expect(business.length).toBeGreaterThan(0);
    expect(technical.length).toBeGreaterThan(0);
  });

  it("splits Markdown into the two tabs without their headings", () => {
    // TECH: either order works; a missing section is "".
    expect(splitExplanation("## Business\nA\n\n## Technical\nB\n")).toEqual({ business: "A", technical: "B" });
    expect(splitExplanation("## Technical\nB\n## Business\nA")).toEqual({ business: "A", technical: "B" });
    expect(splitExplanation("## Business\nonly")).toEqual({ business: "only", technical: "" });
  });
});

describe("captions", () => {
  it("fills {name} placeholders and leaves unknown ones as written", () => {
    expect(fillCaption("{a} of {b} loans", { a: "5", b: 10 })).toBe("5 of 10 loans");
    expect(fillCaption("{missing} stays", {})).toBe("{missing} stays");
  });
});
