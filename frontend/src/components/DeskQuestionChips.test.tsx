/**
 * Tests for components/DeskQuestionChips.tsx.
 * BUSINESS: each desk question shows its label from content/ and its loan count from
 *   the API; one click turns it on, a second click turns it off, and turning on
 *   another replaces the first, so the grid answers one question at a time.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { deskQuestionLabels } from "../content/content";
import { DeskQuestionChips } from "./DeskQuestionChips";

const COUNTS = [
  { id: "ltv_over_125", loans: 20, current_upb: 3.4e6 },
  { id: "new_york", loans: 1101, current_upb: 2.9e7 },
];

describe("DeskQuestionChips", () => {
  it("shows every label from content/, with its count or a loading marker", () => {
    render(<DeskQuestionChips counts={COUNTS} active={null} onChange={vi.fn()} />);
    const chips = screen.getAllByRole("button");
    expect(chips.map((c) => c.firstChild?.textContent)).toEqual(deskQuestionLabels.map((q) => q.label));
    expect(screen.getByRole("button", { name: /LTV over 125/ })).toHaveTextContent("20");
    expect(screen.getByRole("button", { name: /New York/ })).toHaveTextContent("1,101");
    // TECH: no count from the API yet for Puerto Rico in this test.
    expect(screen.getByRole("button", { name: /Puerto Rico/ })).toHaveTextContent("…");
  });

  it("turns a question on, and off again", async () => {
    const onChange = vi.fn();
    const { rerender } = render(<DeskQuestionChips counts={COUNTS} active={null} onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: /New York/ }));
    expect(onChange).toHaveBeenLastCalledWith("new_york");

    rerender(<DeskQuestionChips counts={COUNTS} active="new_york" onChange={onChange} />);
    expect(screen.getByRole("button", { name: /New York/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /LTV over 125/ })).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(screen.getByRole("button", { name: /New York/ }));
    expect(onChange).toHaveBeenLastCalledWith(null);
  });

  it("switches straight from one question to another", async () => {
    const onChange = vi.fn();
    render(<DeskQuestionChips counts={COUNTS} active="new_york" onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: /LTV over 125/ }));
    expect(onChange).toHaveBeenLastCalledWith("ltv_over_125");
  });

  it("explains each chip from the glossary on hover", () => {
    render(<DeskQuestionChips counts={COUNTS} active={null} onChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: /LTV over 125/ })).toHaveAttribute("title", expect.stringMatching(/HARP|refinance/i));
  });
});
