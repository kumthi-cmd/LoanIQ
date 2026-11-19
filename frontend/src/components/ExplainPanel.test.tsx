/**
 * Tests for components/ExplainPanel.tsx.
 * BUSINESS: every screen explains itself; a visitor clicks once to read the
 *   Business and Technical explanation from content/.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ExplainPanel } from "./ExplainPanel";

describe("ExplainPanel", () => {
  it("is closed by default and opens to show both sections", async () => {
    render(<ExplainPanel screen="loan-tape" />);
    const button = screen.getByRole("button", { name: "Explain this screen" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("heading", { name: "Business" })).not.toBeInTheDocument();

    await userEvent.click(button);

    expect(screen.getByRole("button", { name: "Hide explanation" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("heading", { name: "Business" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Technical" })).toBeInTheDocument();
  });

  it("closes again", async () => {
    render(<ExplainPanel screen="loan-tape" />);
    await userEvent.click(screen.getByRole("button", { name: "Explain this screen" }));
    await userEvent.click(screen.getByRole("button", { name: "Hide explanation" }));
    expect(screen.queryByRole("heading", { name: "Business" })).not.toBeInTheDocument();
  });
});
