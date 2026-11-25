/**
 * Tests for components/ExplainPanel.tsx.
 * BUSINESS: every screen explains itself. A visitor reads the Business side first,
 *   switches to Technical with a click or the arrow keys, and looks up the screen's
 *   terms in the glossary card, all from content/ (never from the code).
 * TECH: React Testing Library finds elements by role and name, the way a screen
 *   reader would; userEvent simulates real clicks and key presses.
 */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { lookupTerm, screenTerms } from "../content/content";
import { ExplainPanel } from "./ExplainPanel";

const renderPanel = (onClose = vi.fn()) => {
  render(<ExplainPanel screen="loan-tape" onClose={onClose} />);
  return within(screen.getByRole("complementary", { name: "Screen explanation" }));
};

describe("ExplainPanel", () => {
  it("opens on the Business tab with the business text from content/", () => {
    const panel = renderPanel();
    expect(panel.getByRole("tab", { name: "Business" })).toHaveAttribute("aria-selected", "true");
    expect(panel.getByRole("tab", { name: "Technical" })).toHaveAttribute("aria-selected", "false");
    expect(panel.getByRole("tabpanel")).toHaveTextContent(/first look at a pool of loans/);
    expect(panel.getByRole("tabpanel")).not.toHaveTextContent(/parameterized SQL/);
  });

  it("switches to the Technical text on click", async () => {
    const panel = renderPanel();
    await userEvent.click(panel.getByRole("tab", { name: "Technical" }));
    expect(panel.getByRole("tab", { name: "Technical" })).toHaveAttribute("aria-selected", "true");
    expect(panel.getByRole("tabpanel")).toHaveTextContent(/parameterized SQL/);
  });

  it("moves between tabs with the arrow keys (WAI-ARIA tabs pattern)", async () => {
    const panel = renderPanel();
    panel.getByRole("tab", { name: "Business" }).focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(panel.getByRole("tab", { name: "Technical" })).toHaveFocus();
    expect(panel.getByRole("tab", { name: "Technical" })).toHaveAttribute("aria-selected", "true");
  });

  it("shows the first glossary term and swaps it from a term chip", async () => {
    // BUSINESS: WAC first, the number that decides which coupons a pool fits.
    const panel = renderPanel();
    const first = screenTerms["loan-tape"][0];
    expect(panel.getByText(`Glossary · ${first}`)).toBeInTheDocument();
    expect(panel.getByRole("button", { name: first })).toHaveAttribute("aria-pressed", "true");

    await userEvent.click(panel.getByRole("button", { name: "FICO" }));
    expect(panel.getByText("Glossary · FICO")).toBeInTheDocument();
    expect(panel.getByText(lookupTerm("FICO")!.definition)).toBeInTheDocument();
  });

  it("reports close from its close button", async () => {
    const onClose = vi.fn();
    const panel = renderPanel(onClose);
    await userEvent.click(panel.getByRole("button", { name: "Close explanation" }));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("switches to the Product Slotting explanation and its glossary terms (Step 5b)", async () => {
    // BUSINESS: the Loan Tape explains its own screen and its Product Slotting action.
    render(<ExplainPanel screen="loan-tape" onClose={() => undefined} choicesLabel="Explain"
      choices={[{ screen: "loan-tape", label: "Loan Tape" }, { screen: "product-slotting", label: "Product Slotting" }]} />);
    const panel = within(screen.getByRole("complementary", { name: "Screen explanation" }));
    const choice = within(panel.getByRole("group", { name: "Explain" }));
    expect(choice.getByRole("button", { name: "Loan Tape" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(choice.getByRole("button", { name: "Product Slotting" }));
    expect(choice.getByRole("button", { name: "Product Slotting" })).toHaveAttribute("aria-pressed", "true");
    expect(panel.getByRole("tabpanel")).toHaveTextContent(/where can this loan go/);
    expect(panel.getByText(`Glossary · ${screenTerms["product-slotting"][0]}`)).toBeInTheDocument();
  });
});
