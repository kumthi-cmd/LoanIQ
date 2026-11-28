/**
 * price-grid.spec.ts: a visitor reads the desk's price file (Step 6c).
 *
 * Where it sits: test.ps1 builds the SPA -> Playwright starts FastAPI (config) ->
 * [this spec] opens /prices in a real Chromium against the real price file.
 *
 * BUSINESS: protects what a first-time visitor does on the Price Grid: open it from
 *   the sidebar, see the "Illustrative" line and six products, read a TBA price in
 *   32nds with its decimal on hover, switch to all 25 coupons, pick another product's
 *   pay-ups, and open the explanation.
 * TECH:
 *   - The server builds the price file from Treasury's live curve (or its recorded
 *     fallback when Treasury cannot be reached), so the numbers change every day.
 *     The tests check shapes ("98-08+", "6.290%"), never values; the exact numbers
 *     are covered by the back-end and Vitest tests.
 *   - The first request of a New York day can wait for Treasury (up to the back
 *     end's 5 s timeout), so the first wait allows 15 s.
 *   - Elements are found by role and visible text (.claude/rules/e2e.md).
 */
import { expect, test, type Page } from "@playwright/test";

/** BUSINESS: a TBA price in 32nds: points, a dash, two digits, an optional "+". */
const PRICE_32NDS = /^\d{2,3}-\d{2}\+?$/;

/** TECH: open the Price Grid and wait for the price file to arrive. */
async function openPriceGrid(page: Page) {
  await page.goto("/prices");
  await expect(page.getByText(/^Illustrative, as of \d{4}-\d{2}-\d{2}$/)).toBeVisible({ timeout: 15_000 });
}

test("the Price Grid opens from the sidebar with six products and prices in 32nds", async ({ page }) => {
  await page.goto("/");
  const nav = page.getByRole("navigation", { name: "Screens" });
  await nav.getByRole("link", { name: "Price Grid" }).click();
  await expect(page).toHaveURL(/\/prices$/);
  await expect(nav.getByRole("link", { name: "Price Grid" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("heading", { level: 2, name: "Price Grid" })).toBeVisible();
  await expect(page.getByText(/^Illustrative, as of /)).toBeVisible({ timeout: 15_000 });

  // BUSINESS: six product cards, each with a current coupon in percent (three decimals).
  const cards = page.getByRole("region", { name: "Products" }).getByRole("article");
  await expect(cards).toHaveCount(6);
  await expect(cards.first().getByText(/^\d+\.\d{3}%$/)).toBeVisible();

  // BUSINESS: the first priced cell reads as a TBA price, with its decimal on hover.
  const table = page.getByRole("table", { name: "TBA prices · Current month" });
  const firstPrice = table.getByRole("row").nth(2).getByRole("cell").first();
  // TECH: the cell may end with hidden words for screen readers ("(model-only)"), so
  //   only its first word is the price.
  const text = (await firstPrice.innerText()).trim().split(/\s+/)[0];
  expect(text).toMatch(PRICE_32NDS);
  await expect(firstPrice).toHaveAttribute("title", /: \d{2,3}\.\d+ points/);
});

test("one switch shows all 25 coupons in both tables, and the chips change the pay-ups", async ({ page }) => {
  await openPriceGrid(page);
  const table = page.getByRole("table", { name: "TBA prices · Current month" });
  const traded = await table.getByRole("rowheader").count();
  expect(traded).toBeLessThan(25);

  await page.getByRole("button", { name: "All 25" }).click();
  await expect(table.getByRole("rowheader")).toHaveCount(25);
  const payups = page.getByRole("table", { name: "Spec pay-ups over TBA · UMBS 30" });
  await expect(payups.getByRole("columnheader", { name: "1.0", exact: true })).toBeVisible();

  await page.getByRole("group", { name: "Product" }).getByRole("button", { name: "GNMA II 30" }).click();
  await expect(page.getByRole("table", { name: "Spec pay-ups over TBA · GNMA II 30" })).toBeVisible();
});

test("the explanation opens with its Business and Technical tabs and the glossary", async ({ page }) => {
  await openPriceGrid(page);
  await page.getByRole("button", { name: "Explain this screen" }).click();
  const panel = page.getByRole("complementary", { name: "Screen explanation" });
  await expect(panel.getByText(/This is the desk's price file/)).toBeVisible();
  await expect(panel.getByText("Glossary · Current coupon")).toBeVisible();
  await panel.getByRole("tab", { name: "Technical" }).click();
  await expect(panel.getByText(/GET \/api\/prices\/grid/).first()).toBeVisible();
});
