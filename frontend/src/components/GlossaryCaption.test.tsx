/**
 * Tests for components/GlossaryCaption.tsx.
 * BUSINESS: a caption's marked words explain themselves on hover, and the words
 *   themselves stay in content/; a visitor never sees the [[ ]] markers.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { captionText, GlossaryCaption, splitGlossaryCaption } from "./GlossaryCaption";

describe("splitGlossaryCaption", () => {
  it("splits text and terms, with or without shown words", () => {
    expect(splitGlossaryCaption("Price and [[Drop|drop]] in [[32nds]]")).toEqual([
      { text: "Price and " }, { term: "Drop", text: "drop" }, { text: " in " }, { term: "32nds", text: "32nds" },
    ]);
  });

  // TECH: the plain form names a table without the hidden definitions.
  it("gives the plain words for an accessible name", () => {
    expect(captionText("Spec [[Pay-up|pay-ups]] over TBA")).toBe("Spec pay-ups over TBA");
    expect(captionText("[[32nds]]")).toBe("32nds");
  });

  it("leaves text with no markers, or an unclosed one, as it is", () => {
    expect(splitGlossaryCaption("No terms here")).toEqual([{ text: "No terms here" }]);
    expect(splitGlossaryCaption("Broken [[Drop")).toEqual([{ text: "Broken [[Drop" }]);
    expect(splitGlossaryCaption("")).toEqual([]);
  });
});

describe("GlossaryCaption", () => {
  it("shows the words without markers and links the term to its definition", () => {
    const { container } = render(<p><GlossaryCaption text="Spec [[Pay-up|pay-ups]] over TBA" /></p>);
    expect(container.querySelector("p")?.textContent).toMatch(/^Spec pay-ups.* over TBA$/);
    expect(container.textContent).not.toContain("[[");
    expect(screen.getByText("pay-ups")).toHaveAttribute("title", expect.stringMatching(/spec pool is worth over the TBA/));
  });
});
