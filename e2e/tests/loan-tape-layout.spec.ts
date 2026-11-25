/**
 * loan-tape-layout.spec.ts: the Loan Tape screen's layout at 1440 px, the width the
 * "1 · Loan Tape" design board is drawn for.
 *
 * Where it sits: test.ps1 builds the SPA -> Playwright starts FastAPI -> [this spec]
 * measures the real screen in Chromium. It closes the Step 1d follow-ups (Step 1g).
 *
 * BUSINESS: a trader on a 1440 px laptop sees the whole default tape (12 columns)
 *   without scrolling sideways, and the panel titles and desk-question chips each on
 *   one line, whether or not the explanation is open. Since Step 5b the middle panel
 *   is Slotting (it replaced the note-rate distribution and its axis), and these
 *   checks run on an unslotted tape: the Product Slotting spec runs after this one
 *   (playwright.config.ts), because slotted, the grid gains two columns that scroll.
 * TECH: elements are found by role and visible text (.claude/rules/e2e.md); sizes come
 *   from boundingBox() in CSS pixels. Measured on 2026-11-23: all 12 columns in
 *   1,156 px with the explanation closed, 8 with it open; "8.0%" and "9%+" 29 px apart
 *   closed and 8 px open. The checks leave a little room for font rendering.
 */
import { expect, test, type Locator, type Page } from "@playwright/test";

test.use({ viewport: { width: 1440, height: 900 } });

/** TECH: open the Loan Tape and wait until the first block of loans is drawn. */
async function openTape(page: Page) {
  await page.goto("/");
  await expect(page.getByRole("columnheader", { name: "Loan ID" })).toBeVisible();
  await expect(page.getByTestId("row-count")).not.toHaveText("… loans");
}

/** TECH: true if a box lies wholly inside another (1 px tolerance for rounding). */
async function inside(inner: Locator, outer: Locator): Promise<boolean> {
  const a = await inner.boundingBox();
  const b = await outer.boundingBox();
  return !!a && !!b && a.x >= b.x - 1 && a.x + a.width <= b.x + b.width + 1;
}

/** The column headers wholly inside the grid's frame, as their visible names. */
async function fullyVisibleColumns(page: Page): Promise<string[]> {
  const grid = page.getByRole("region", { name: "Loan grid" });
  const names: string[] = [];
  for (const header of await grid.getByRole("columnheader").all()) {
    // TECH: textContent, not innerText: CSS shows headers in upper case, and innerText
    //   returns the text as styled ("LOAN ID"), textContent as written ("Loan ID").
    const name = ((await header.textContent()) ?? "").trim();
    if (name && (await inside(header, grid))) names.push(name);
  }
  return names;
}

/** TECH: the number of distinct rows a set of elements sits on, by their top edge. */
async function rowsUsed(items: Locator): Promise<number> {
  const tops = new Set<number>();
  for (const item of await items.all()) tops.add(Math.round((await item.boundingBox())!.y));
  return tops.size;
}

/** Checks that hold with the explanation open or closed. */
async function expectOneLineTitlesAndChips(page: Page) {
  // BUSINESS: each panel title stays on one line, as on the board.
  // TECH: the title's box can be taller than its text (it stretches to the height of
  //   a wrapped caption beside it), so count the lines of the text itself: a DOM Range
  //   over the title's own text node gives one rectangle per line fragment; distinct
  //   tops = lines. The text node is found by its words inside the panel (region),
  //   because a glossary-linked title (MBA delinquency) also holds its hidden
  //   definition, so the element's whole text is more than the title.
  for (const name of ["Program mix", "Slotting", "MBA delinquency"]) {
    const lines = await page.getByRole("region", { name }).evaluate((panel, title) => {
      const walker = document.createTreeWalker(panel, NodeFilter.SHOW_TEXT);
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        if (node.textContent?.trim() !== title) continue;
        const range = document.createRange();
        range.selectNodeContents(node);
        return new Set([...range.getClientRects()].map((r) => Math.round(r.top))).size;
      }
      return 0; // TECH: title not found: fails the check below
    }, name);
    expect(lines, name).toBe(1);
  }

  // BUSINESS: all six desk-question chips on one row, Forbearance included.
  const chips = page.getByRole("group", { name: "Desk questions" }).getByRole("button");
  await expect(chips).toHaveCount(6);
  expect(await rowsUsed(chips)).toBe(1);
}

test("at 1440 px with the explanation closed, all 12 default columns fit and nothing wraps", async ({ page }) => {
  await openTape(page);
  // BUSINESS: closed is the default since Step 1g.
  await expect(page.getByRole("button", { name: "Explain this screen" })).toHaveAttribute("aria-expanded", "false");
  const columns = await fullyVisibleColumns(page);
  expect(columns).toHaveLength(12);
  expect(columns).toEqual(expect.arrayContaining(["Loan ID", "Seller", "Occupancy", "State", "DQ Status"]));
  await expectOneLineTitlesAndChips(page);
});

test("at 1440 px with the explanation open, the first 8 columns fit and nothing wraps", async ({ page }) => {
  await openTape(page);
  await page.getByRole("button", { name: "Explain this screen" }).click();
  await expect(page.getByRole("complementary", { name: "Screen explanation" })).toBeVisible();
  // BUSINESS: Loan ID through DTI, in the tape's column order, before the grid scrolls.
  const columns = await fullyVisibleColumns(page);
  expect(columns.slice(0, 8)).toEqual(
    ["Loan ID", "Seller", "Program", "Product", "Note Rate (%)", "Current UPB ($)", "FICO", "DTI (%)"],
  );
  await expectOneLineTitlesAndChips(page);
});
