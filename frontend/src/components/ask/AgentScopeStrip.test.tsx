/**
 * Tests for components/ask/AgentScopeStrip.tsx, the "Knows: Tape ✓ · Slotting –" strip.
 *
 * BUSINESS: protects "the visitor can see what the agent knows": the tape is known,
 *   Product Slotting is "not run yet" until the desk runs it and "known" after, and
 *   the later stages say they are coming, each in words a screen reader speaks.
 * TECH: the status shapes are the generated API type (AskStatus); words come from
 *   content/ask-the-tape.json "scope".
 */
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { AskStatus } from "../../api/types";
import { AgentScopeStrip } from "./AgentScopeStrip";

const STAGES = ["tape", "slotting", "bestex", "optimization", "pooling", "trading"];
const status = (slotting: string): AskStatus => ({
  mode: "model", reason: null, notice: null,
  stages: STAGES.map((id, i) => ({
    id, step: [1, 5, 6, 8, 8, 7][i],
    state: id === "tape" ? "known" : id === "slotting" ? slotting : "planned",
  })),
});

describe("AgentScopeStrip", () => {
  it("shows every stage, with slotting not run yet before a run", () => {
    render(<AgentScopeStrip status={status("not_run")} />);
    const list = screen.getByRole("list", { name: "What Ask the Tape knows" });
    const items = within(list).getAllByRole("listitem");
    expect(items.map((li) => li.textContent?.split(",")[0].replace(/[✓–]/, ""))).toEqual(
      ["Tape", "Slotting", "BestEx", "Optimization", "Pooling", "Trading"]);
    expect(items[0]).toHaveTextContent("known");
    expect(items[1]).toHaveTextContent("not run yet");
    expect(items[2]).toHaveTextContent("coming in a later step");
  });

  it("marks slotting known once the desk has run it", () => {
    render(<AgentScopeStrip status={status("known")} />);
    const slotting = screen.getAllByRole("listitem")[1];
    expect(slotting).toHaveTextContent("✓");
    expect(slotting).toHaveAttribute("title", "Slotting: known");
  });

  it("shows nothing before the status arrives", () => {
    const { container } = render(<AgentScopeStrip status={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
