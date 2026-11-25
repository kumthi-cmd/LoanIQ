/**
 * product-slotting.spec.ts: end-to-end test of Product Slotting on the Loan Tape (Step 5b).
 *
 * BUSINESS: what a visitor does on the "5 · Product Slotting" board: click Product
 *   Slotting in the sidebar, read what will run, run it, watch the commentary to the
 *   totals, land on the updated Loan Tape with Slot and Spec Stories, and hover the
 *   board's loan (LN78265415) to see UMBS 30Y at 2.5 / 3.0 with LLB 275K, NY and Low
 *   FICO. Every number checked comes from the API, not from the board.
 * TECH:
 *   - A run changes the one shared server for every test after it, so this file runs
 *     in its own Playwright project that depends on the main one and so runs last
 *     (playwright.config.ts). Each test stands alone: the first runs slotting through
 *     the screen; the others make sure the tape is slotted through the API
 *     (ensureSlotted) before they start.
 *   - Elements by role and visible text (.claude/rules/e2e.md). The real pacing runs
 *     (about 5 s), well inside the test timeout.
 */
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const fmt = (n: number) => n.toLocaleString("en-US");
const BOARD_LOAN = "LN78265415";

/**
 * BUSINESS: the tape is slotted before a test that needs it.
 * TECH: POST /api/slotting/run reads the whole stream; a run is quick on the server.
 */
async function ensureSlotted(request: APIRequestContext) {
  const status = await (await request.get("/api/slotting/status")).json();
  if (!status.run) expect((await request.post("/api/slotting/run")).ok()).toBe(true);
}

/** TECH: open the Loan Tape and wait until the first block of loans is drawn. */
async function openTape(page: Page) {
  await page.goto("/");
  await expect(page.getByRole("columnheader", { name: "Loan ID" })).toBeVisible();
  await expect(page.getByTestId("row-count")).not.toHaveText("… loans");
}

test("runs Product Slotting from the sidebar and updates the Loan Tape", async ({ page, request }) => {
  const tape = await (await request.get("/api/tape")).json();
  await openTape(page);
  const nav = page.getByRole("navigation", { name: "Screens" });
  const action = nav.getByRole("button", { name: /Product Slotting/ });
  // TECH: the main project never slots, so the tape is unslotted here on a full run.
  await expect(action).toContainText(/Not run on this tape|Last run/);

  // BUSINESS: the confirm dialog says what will run, from the API.
  await action.click();
  const dialog = page.getByRole("dialog", { name: "Run Product Slotting?" });
  await expect(dialog).toContainText(`${fmt(tape.loans)} loans · ${tape.fields} fields`);
  await expect(dialog).toContainText(/\d+ rules in \d+ spec stories: LLB tiers/);
  await dialog.getByRole("button", { name: "Run slotting" }).click();

  // BUSINESS: the commentary, then the totals; then the dialog closes by itself.
  const running = page.getByRole("dialog");
  await expect(running.getByRole("heading", { name: "Slotting the tape" })).toBeVisible();
  await expect(running.getByRole("heading", { name: "Loan Tape updated" })).toBeVisible({ timeout: 15_000 });
  const status = await (await request.get("/api/slotting/status")).json();
  const t = status.totals;
  await expect(running).toContainText(`${fmt(t.slotted)} of ${fmt(t.loans)} loans slotted`);
  await expect(running.getByRole("listitem")).toHaveCount(13);
  await expect(running).toContainText(`${fmt(t.by_reason.no_agency)} Jumbo and Non-QM loans have no agency pool`);
  await expect(page.getByRole("dialog")).toHaveCount(0, { timeout: 5_000 });

  // BUSINESS: the Loan Tape now says what changed, and has the two new columns.
  await expect(page.getByRole("status")).toContainText("Loan Tape updated by Product Slotting");
  await expect(page.getByRole("columnheader", { name: "Slot" })).toBeAttached();
  await expect(page.getByRole("columnheader", { name: "Spec Stories" })).toBeAttached();
  await expect(action).toContainText(/Last run \d{1,2}:\d{2} (AM|PM)/);
  const panel = page.getByRole("region", { name: "Slotting" });
  await expect(panel).toContainText("LLB tiers");
  await expect(panel).toContainText(fmt(t.stories.LLB));
});

test("hovering the board's loan shows its coupons and three spec stories", async ({ page, request }) => {
  await ensureSlotted(request);
  const card = await (await request.get(`/api/loans/${BOARD_LOAN}/slots`)).json();
  await openTape(page);
  await page.getByRole("textbox", { name: "Loan ID Filter Input" }).fill(BOARD_LOAN);
  await expect(page.getByTestId("row-count")).toHaveText("1 loan");
  const grid = page.getByRole("region", { name: "Loan grid" });
  await grid.getByText(BOARD_LOAN, { exact: true }).hover();
  const tip = page.getByRole("tooltip");
  await expect(tip).toContainText(`${card.agency} ${card.term}`);
  await expect(tip).toContainText(`Down ${card.down_coupon} · Up ${card.up_coupon}`);
  for (const story of card.stories) await expect(tip).toContainText(`${story.label} spec`);
  await expect(tip).toContainText("LLB 275K spec");
  await expect(tip).toContainText(card.generic_tba);

  // BUSINESS: the row's Spec Stories cell shows the same stories as pills.
  await page.mouse.move(0, 0);
  await expect(page.getByRole("tooltip")).toHaveCount(0);
  await expect(grid.getByText("Low FICO", { exact: true })).toBeAttached();
});

test("Spec Stories filters like any column, with the run's count", async ({ page, request }) => {
  await ensureSlotted(request);
  const status = await (await request.get("/api/slotting/status")).json();
  await openTape(page);
  await page.getByRole("textbox", { name: "Spec Stories Filter Input" }).fill("Generic TBA");
  // TECH: the floating filter uses "contains"; only generic TBA loans contain that text.
  await expect(page.getByTestId("row-count")).toHaveText(`${fmt(status.totals.generic_tba)} loans`);
});
