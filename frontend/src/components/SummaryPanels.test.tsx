/**
 * Tests for the three Loan Tape panels: ProgramMixPanel, NoteRatePanel, DelinquencyPanel.
 * BUSINESS: each panel shows the API's numbers in the desk's units ($ millions for
 *   balance, loans for delinquency), in the order a trader reads them, with the
 *   largest bar full length, red only for late loans, and a loading marker until the
 *   numbers arrive (never a misleading zero).
 */
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { RateBucket } from "../api/types";
import { DelinquencyPanel } from "./DelinquencyPanel";
import { NoteRatePanel } from "./NoteRatePanel";
import { ProgramMixPanel } from "./ProgramMixPanel";

const region = (name: string) => within(screen.getByRole("region", { name }));
// TECH: the browser rewrites "100.0%" as "100%" in an inline style, so bar sizes are
//   compared as numbers (percent of the largest bar), not as text.
const sizes = (items: HTMLElement[], selector: string, prop: "width" | "height") =>
  items.map((el) => parseFloat(el.querySelector<HTMLElement>(selector)!.style[prop]));

describe("ProgramMixPanel", () => {
  it("shows each program's balance in $M, largest first and full width", () => {
    render(<ProgramMixPanel programs={[
      { program: "Conventional", loans: 1014, current_upb: 212_804_314.92 },
      { program: "USDA", loans: 60, current_upb: 8_144_422.3 },
    ]} />);
    const rows = region("Program mix").getAllByRole("listitem");
    expect(rows.map((r) => r.textContent)).toEqual([expect.stringMatching(/^Conventional.*212\.8$/),
      expect.stringMatching(/^USDA.*8\.1$/)]);
    expect(sizes(rows, ".bar-fill", "width")).toEqual([100, 3.8]);
    // BUSINESS: hovering a program name explains it from the glossary.
    expect(region("Program mix").getByText("Conventional")).toHaveAttribute("title", expect.stringMatching(/GSEs/));
  });

  it("shows a loading marker before the API answers", () => {
    render(<ProgramMixPanel programs={null} />);
    expect(region("Program mix").getByText("…")).toBeInTheDocument();
  });
});

describe("NoteRatePanel", () => {
  const buckets: RateBucket[] = [
    { low: null, high: 2.5, loans: 3, current_upb: 3_230_000 },
    { low: 2.5, high: 3, loans: 0, current_upb: 0 },
    { low: 3, high: null, loans: 9, current_upb: 114_940_000 },
  ];

  it("draws one bar per bucket, scaled to the largest, with readable text for each", () => {
    render(<NoteRatePanel buckets={buckets} />);
    const bars = region("Note rate distribution").getAllByRole("listitem");
    expect(bars).toHaveLength(3);
    expect(sizes(bars, ".histogram-bar", "height")).toEqual([2.8, 0, 100]);
    // BUSINESS: an empty bucket is a visible gap, still described in words.
    expect(bars[1]).toHaveTextContent("2.5–3.0%: $0.0M, 0 loans");
    expect(bars[2]).toHaveAttribute("title", "3.0%+: $114.9M, 9 loans");
  });

  it("says why the distribution matters, from content/", () => {
    render(<NoteRatePanel buckets={buckets} />);
    expect(screen.getByText(/WAC alone hides this shape/)).toBeInTheDocument();
  });

  // BUSINESS: the board's short caption, with the bucket width from the data (Step 1g).
  it("captions the panel with the bucket width read from the data", () => {
    render(<NoteRatePanel buckets={buckets} />);
    expect(region("Note rate distribution").getByText("UPB by 0.5% bucket")).toBeInTheDocument();
  });

  // TECH: the first label starts at the axis edge, middle ticks are centred on their
  //   bucket edge, and the open-ended last label is right-aligned (styles.css).
  it("places the first, middle and open-ended axis labels", () => {
    const four: RateBucket[] = [
      { low: null, high: 2.5, loans: 1, current_upb: 1 }, { low: 2.5, high: 3, loans: 1, current_upb: 1 },
      { low: 3, high: 3.5, loans: 1, current_upb: 1 }, { low: 3.5, high: 4, loans: 1, current_upb: 1 },
      { low: 4, high: 4.5, loans: 1, current_upb: 1 }, { low: 4.5, high: null, loans: 1, current_upb: 1 },
    ];
    const { container } = render(<NoteRatePanel buckets={four} />);
    const slots = [...container.querySelectorAll(".histogram-axis > span")];
    expect(slots.map((s) => s.textContent)).toEqual(["2.0%", "", "", "", "4.0%", "4.5%+"]);
    expect(slots[0]).not.toHaveClass("histogram-axis-tick");
    expect(slots[4]).toHaveClass("histogram-axis-tick");
    expect(slots[5]).toHaveClass("histogram-axis-end");
  });
});

describe("DelinquencyPanel", () => {
  it("headlines Current with its share, then each late status in red", () => {
    render(<DelinquencyPanel statuses={[
      { status: "Current", loans: 1848, current_upb: 6e8 },
      { status: "30", loans: 65, current_upb: 2e7 },
      { status: "REO", loans: 0, current_upb: 0 },
      { status: "BK", loans: 87, current_upb: 3e7 },
    ]} />);
    const panel = region("MBA delinquency");
    expect(panel.getByText("1,848")).toBeInTheDocument();
    expect(panel.getByText("· 92.4% of loans")).toBeInTheDocument();
    const rows = panel.getAllByRole("listitem");
    expect(rows.map((r) => r.textContent)).toEqual(["3065", "REO0", "BK87"]);
    expect(within(rows[0]).getByText("30")).toHaveClass("dq-delinquent");
    expect(sizes(rows, ".bar-fill", "width")).toEqual([74.7, 0, 100]);
  });

  it("shows a dash, not 0%, for an empty tape", () => {
    render(<DelinquencyPanel statuses={[{ status: "Current", loans: 0, current_upb: 0 }]} />);
    expect(region("MBA delinquency").getByText("· — of loans")).toBeInTheDocument();
  });
});
