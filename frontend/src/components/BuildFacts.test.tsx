/**
 * Tests for BuildFacts (the "By the numbers" tiles) and parseBuildFacts.
 *
 * BUSINESS: the How it was built page shows the real numbers from the last full test
 *   run, formatted for reading, and never breaks or shows "NaN" when the committed
 *   content/build-facts.json is older, partial or hand-edited.
 * TECH: renders the component with plain objects; parseBuildFacts is a pure function.
 */
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { buildFacts, parseBuildFacts } from "../content/content";
import { BuildFacts, MISSING } from "./BuildFacts";

/** TECH: the value shown next to a label, read through the <dt>/<dd> pairing. */
function valueOf(label: string): string | null {
  const term = screen.getByText(label, { selector: "dt" });
  return term.nextElementSibling?.textContent ?? null;
}

describe("BuildFacts", () => {
  it("shows every fact, with thousands separators and coverage in percent", () => {
    render(<BuildFacts facts={{ backendTests: 1226, frontendTests: 104, e2eTests: 14,
      backendCoverage: 98.84, commits: 13, date: "2026-11-23" }} />);
    expect(within(screen.getByLabelText("By the numbers")).getAllByRole("term")).toHaveLength(6);
    expect(valueOf("Back-end tests")).toBe("1,226");
    expect(valueOf("Front-end tests")).toBe("104");
    expect(valueOf("End-to-end tests")).toBe("14");
    // BUSINESS: coverage to one decimal, against the 80% floor.
    expect(valueOf("Back-end coverage")).toBe("98.8%");
    expect(valueOf("Commits")).toBe("13");
    expect(valueOf("Last full test run")).toBe("2026-11-23");
  });

  // BUSINESS: the page still renders when a number is missing (Step 1f requirement).
  it("shows a dash for every missing fact", () => {
    render(<BuildFacts facts={{ e2eTests: 14 }} />);
    expect(valueOf("End-to-end tests")).toBe("14");
    for (const label of ["Back-end tests", "Front-end tests", "Back-end coverage", "Commits", "Last full test run"]) {
      expect(valueOf(label)).toBe(MISSING);
    }
  });
});

describe("parseBuildFacts", () => {
  it("keeps well-typed fields", () => {
    expect(parseBuildFacts({ backendTests: 5, backendCoverage: 0, date: "2026-11-23" }))
      .toEqual({ backendTests: 5, backendCoverage: 0, date: "2026-11-23" });
  });

  // TECH: strings, NaN, negatives, empty dates and unknown keys are dropped, not shown.
  it("drops anything that is not a usable number or date", () => {
    expect(parseBuildFacts({ backendTests: "226", frontendTests: Number.NaN, e2eTests: -1,
      commits: Infinity, date: "", extra: 1 })).toEqual({});
    expect(parseBuildFacts(null)).toEqual({});
    expect(parseBuildFacts([1, 2])).toEqual({});
  });

  // BUSINESS: the committed file is complete, so the live site shows every number.
  it("reads all six facts from the committed content/build-facts.json", () => {
    expect(Object.keys(buildFacts).sort()).toEqual(
      ["backendCoverage", "backendTests", "commits", "date", "e2eTests", "frontendTests"],
    );
    expect(buildFacts.date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});
