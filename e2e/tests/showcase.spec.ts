/**
 * showcase.spec.ts: a visitor opens About and How it was built from the sidebar.
 *
 * Where it sits: test.ps1 builds the SPA -> Playwright starts FastAPI (config) ->
 * [this spec] clicks the Showcase links in a real Chromium.
 *
 * BUSINESS: protects the two pages that tell a first-time visitor what LoanIQ is and
 *   how it was built AI-first: both open from the sidebar, show their words from
 *   content/, the About logo really loads, and How it was built shows the numbers and
 *   the build log.
 * TECH: elements are found by role and visible text (.claude/rules/e2e.md). Each test
 *   starts from the Loan Tape at "/" and clicks, like a visitor, so the router's
 *   in-app navigation is what is tested (deep-link reloads are in loan-tape.spec.ts).
 */
import { expect, test, type Page } from "@playwright/test";

/** TECH: open LoanIQ and click one Showcase link in the sidebar. */
async function openFromSidebar(page: Page, label: string) {
  await page.goto("/");
  const nav = page.getByRole("navigation", { name: "Screens" });
  await nav.getByRole("link", { name: label }).click();
  // BUSINESS: the sidebar shows where the visitor is.
  await expect(nav.getByRole("link", { name: label })).toHaveAttribute("aria-current", "page");
}

test("About opens from the sidebar with the stacked logo above the text", async ({ page }) => {
  await openFromSidebar(page, "About");
  await expect(page).toHaveURL(/\/about$/);
  const heading = page.getByRole("heading", { name: "About LoanIQ" });
  await expect(heading).toBeVisible();
  await expect(page.getByRole("heading", { name: "What LoanIQ does" })).toBeVisible();
  // TECH: the logo is decorative (alt=""), so Playwright's role queries skip it;
  //   it is the only image inside the main area.
  const logo = page.getByRole("main").locator("img");
  await expect(logo).toHaveCount(1);
  await expect.poll(() => logo.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0))
    .toBe(true);
  // BUSINESS: the logo sits above the words.
  const logoBox = await logo.boundingBox();
  const headingBox = await heading.boundingBox();
  expect(logoBox!.y + logoBox!.height).toBeLessThanOrEqual(headingBox!.y);
});

test("How it was built opens from the sidebar with the numbers and the build log", async ({ page }) => {
  await openFromSidebar(page, "How it was built");
  await expect(page).toHaveURL(/\/how-it-was-built$/);
  await expect(page.getByRole("heading", { name: /How LoanIQ was built/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "By the numbers" })).toBeVisible();
  // BUSINESS: the committed facts are shown, so each tile holds a number, not a dash.
  const facts = page.getByLabel("By the numbers");
  await expect(facts.getByRole("term")).toHaveCount(6);
  await expect(facts.getByText("Back-end tests")).toBeVisible();
  for (const value of await facts.getByRole("definition").allTextContents()) {
    expect(value).toMatch(/\d/);
  }
  await expect(page.getByRole("heading", { name: "Build log" })).toBeVisible();
  await expect(page.getByRole("heading", { name: /^Hosting, LoanIQ online/ })).toBeVisible();
});
