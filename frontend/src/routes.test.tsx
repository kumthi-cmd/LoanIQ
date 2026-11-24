/**
 * Tests that every live sidebar entry opens its own screen, and the Showcase pages.
 *
 * BUSINESS: protects a visitor from a sidebar link that leads nowhere: every screen
 *   marked live in nav.ts must have a route in App.tsx that draws a real screen, not
 *   "Screen not found". The About and How it was built pages must show their words
 *   from content/, the logo, the "By the numbers" facts and the build log.
 * TECH: the real routes in a memory router, one render per live path. fetch is mocked
 *   to answer every API call with an empty 404, so the Loan Tape screen renders its
 *   frame (its data is covered by App.test.tsx); LoanGrid is stubbed because AG Grid
 *   needs real layout that jsdom lacks. A new live screen is picked up automatically.
 */
import { render, screen } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { routes } from "./App";
import { NAV_ITEMS } from "./nav";

vi.mock("./components/LoanGrid", () => ({ LoanGrid: () => <div>grid stub</div> }));

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({
    ok: false, status: 404, statusText: "", json: () => Promise.resolve({ detail: "not found" }),
  })));
});
afterEach(() => vi.unstubAllGlobals());

const renderAt = (path: string) =>
  render(<RouterProvider router={createMemoryRouter(routes, { initialEntries: [path] })} />);

describe("live routes", () => {
  const live = NAV_ITEMS.filter((item) => item.live);

  // BUSINESS: Step 1f made three screens live and Step 4b adds Ask the Tape; fewer
  //   would mean a page was lost.
  it("has Loan Tape, Ask the Tape, About and How it was built live", () => {
    expect(live.map((i) => i.path)).toEqual(["/", "/ask", "/about", "/how-it-was-built"]);
  });

  it.each(live.map((i) => [i.label, i.path]))("%s (%s) renders its own screen", (label, path) => {
    renderAt(path);
    expect(screen.queryByRole("heading", { name: "Screen not found" })).not.toBeInTheDocument();
    // BUSINESS: the sidebar marks this entry as the current page.
    expect(screen.getByRole("link", { name: label })).toHaveAttribute("aria-current", "page");
  });

  // TECH: the control case: the "*" route still catches a path no screen owns.
  it("an unknown path shows Screen not found", () => {
    renderAt("/no-such-screen");
    expect(screen.getByRole("heading", { name: "Screen not found" })).toBeInTheDocument();
  });
});

describe("About", () => {
  it("shows the stacked LoanIQ Labs logo above content/about.md", () => {
    const { container } = renderAt("/about");
    // TECH: decorative (alt=""), so it has no accessible name; find it by its file.
    const logo = container.querySelector("img.showcase-logo");
    expect(logo).toHaveAttribute("src", expect.stringContaining("loaniq-labs_stacked_dark-bg"));
    const heading = screen.getByRole("heading", { name: "About LoanIQ" });
    // BUSINESS: the logo comes first, then the words.
    expect(logo!.compareDocumentPosition(heading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByRole("heading", { name: "What LoanIQ does" })).toBeInTheDocument();
  });

  // TECH: Markdown "#" becomes h2, under the header's one h1 (ShowcaseMarkdown).
  it("keeps the header's logo as the only h1", () => {
    renderAt("/about");
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 2, name: "About LoanIQ" })).toBeInTheDocument();
  });
});

describe("How it was built", () => {
  it("shows the approach, then By the numbers, then the build log", () => {
    renderAt("/how-it-was-built");
    const approach = screen.getByRole("heading", { name: /How LoanIQ was built/ });
    const numbers = screen.getByRole("heading", { name: "By the numbers" });
    const log = screen.getByRole("heading", { name: "Build log" });
    const follows = (a: Element, b: Element) => Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
    expect(follows(approach, numbers)).toBe(true);
    expect(follows(numbers, log)).toBe(true);
    // BUSINESS: the tiles sit between the heading and the log.
    const tiles = screen.getByLabelText("By the numbers");
    expect(follows(numbers, tiles)).toBe(true);
    expect(follows(tiles, log)).toBe(true);
    expect(screen.getByText("Back-end tests")).toBeInTheDocument();
  });
});
