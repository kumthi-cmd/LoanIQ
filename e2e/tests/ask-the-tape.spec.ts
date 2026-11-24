/**
 * ask-the-tape.spec.ts: end-to-end tests of the Ask the Tape screen (Step 4b).
 *
 * BUSINESS: protects what a visitor does on Ask the Tape, in a real browser against
 *   the real API and tape:
 *   - Ctrl K or the header box opens the screen with the question filled in, unsent;
 *   - the Offline banner shows while built-in rules answer;
 *   - an answer shows its tool chips, the SQL behind them and its loans;
 *   - a loan ID opens the loan drawer;
 *   - "Open in Loan Tape" shows exactly the same loans in the grid, or says why not;
 *   - a saved query survives a reload and reruns without any model call.
 * TECH: the test server runs with ANTHROPIC_API_KEY blanked (playwright.config.ts),
 *   so the built-in rules answer: free and repeatable. Expected counts come from
 *   the API (`request` fixture), never hard-coded. Elements are found by role and
 *   visible text (.claude/rules/e2e.md). Each test opens the page fresh; Playwright
 *   gives each test a new browser context, so localStorage starts empty.
 */
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const fmt = (n: number) => n.toLocaleString("en-US");

/** TECH: how many loans match a grid filter model, from the loan API. */
async function matching(request: APIRequestContext, filter: object): Promise<number> {
  const params = new URLSearchParams({ limit: "1", filter: JSON.stringify(filter) });
  return (await (await request.get(`/api/loans?${params}`)).json()).total;
}

const LTV_FILTER = { ltv: { filterType: "number", type: "greaterThan", filter: 125 } };

/** Ask one question on the Ask the Tape screen and wait for its answer. */
async function ask(page: Page, question: string) {
  await page.getByRole("textbox", { name: "Ask the tape" }).fill(question);
  await page.getByRole("button", { name: "Send question" }).click();
  await expect(page.getByRole("article", { name: `Question: ${question}` }).getByRole("table").last()).toBeVisible();
}

test("Ctrl K and the header box open Ask the Tape with the question filled in, unsent", async ({ page }) => {
  const modelCalls: string[] = [];
  page.on("request", (r) => {
    if (r.method() === "POST" && new URL(r.url()).pathname === "/api/ask") modelCalls.push(r.url());
  });
  await page.goto("/");
  await page.getByRole("searchbox", { name: /Ask the tape/ }).fill("NY loans under $150K?");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/ask\?q=/);
  const box = page.getByRole("textbox", { name: "Ask the tape" });
  await expect(box).toHaveValue("NY loans under $150K?");
  await expect(box).toBeFocused();

  await page.goto("/about");
  await page.keyboard.press("Control+k");
  await expect(page).toHaveURL(/\/ask$/);
  await expect(page.getByRole("textbox", { name: "Ask the tape" })).toBeFocused();
  // BUSINESS: nothing was sent, so no AI model call was made.
  expect(modelCalls).toEqual([]);
});

test("built-in rules answer with the SQL and the loans, under the Offline banner", async ({ page, request }) => {
  const expected = await matching(request, LTV_FILTER);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/ask");
  await expect(page.getByRole("link", { name: "Ask the Tape" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("status").filter({ hasText: "Offline is answering" })).toBeVisible();
  // BUSINESS: at 1440 px the conversation and the agent's panels sit side by side.
  const convo = await page.getByRole("region", { name: "Conversation" }).boundingBox();
  const side = await page.getByRole("complementary", { name: "Agent workings" }).boundingBox();
  expect(side!.x).toBeGreaterThan(convo!.x + convo!.width - 1);

  await ask(page, "Which loans have an LTV over 125?");
  const chip = page.getByRole("button", { name: `query_tape → ${fmt(expected)} rows` });
  await chip.click();
  await expect(page.getByTestId("tool-detail")).toContainText("ltv > 125");
  await expect(page.getByText(`LTV over 125: ${expected} loans`)).toBeVisible();
  // BUSINESS: the answer itself also says built-in rules wrote it (the banner says so too).
  await expect(page.getByRole("region", { name: "Conversation" }).getByText(/^Answered by built-in rules/)).toBeVisible();
});

test("a loan ID opens the loan drawer with every field", async ({ page, request }) => {
  const fields = (await (await request.get("/api/loans/columns")).json()).length;
  await page.goto("/ask");
  await ask(page, "Which loans have an LTV over 125?");
  const first = page.getByRole("table").last().getByRole("button").first();
  const loanId = (await first.textContent())!;
  await first.click();
  const drawer = page.getByRole("dialog", { name: `Loan ${loanId}` });
  await expect(drawer.getByText("Current UPB ($)")).toBeVisible();
  // BUSINESS: the whole loan: one labelled line per tape field.
  await expect(drawer.getByRole("term")).toHaveCount(fields);
  await page.keyboard.press("Escape");
  await expect(drawer).toHaveCount(0);
});

test("Open in Loan Tape shows the same loans in the grid", async ({ page, request }) => {
  const expected = await matching(request, LTV_FILTER);
  await page.goto("/ask");
  await ask(page, "Which loans have an LTV over 125?");
  await page.getByRole("link", { name: "Open in Loan Tape" }).last().click();
  await expect(page).toHaveURL(/\/\?filter=/);
  await expect(page.getByText("Filtered from Ask the Tape")).toBeVisible();
  await expect(page.getByTestId("row-count")).toHaveText(`${fmt(expected)} loans`);
  await page.getByRole("button", { name: "Show the whole tape" }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByTestId("row-count")).not.toHaveText(`${fmt(expected)} loans`);
});

test("a filter the grid cannot show says why", async ({ page }) => {
  await page.goto("/ask");
  await ask(page, "Which loans are 90+ days late or in foreclosure?");
  // BUSINESS: five delinquency statuses do not fit a grid column's two conditions.
  await expect(page.getByRole("button", { name: "Open in Loan Tape" }).last()).toBeDisabled();
  await expect(page.getByText(/Can't open in the Loan Tape: dq_status is matched against 5 values/).last()).toBeVisible();
});

test("a saved query survives a reload and reruns without the model", async ({ page }) => {
  await page.goto("/ask");
  await ask(page, "Show me the New York loans");
  await page.getByRole("button", { name: "Save query" }).click();
  await expect(page.getByText("Saved as")).toBeVisible();

  await page.reload();
  const modelCalls: string[] = [];
  page.on("request", (r) => {
    if (r.method() === "POST" && new URL(r.url()).pathname === "/api/ask") modelCalls.push(r.url());
  });
  await page.getByRole("button", { name: "Rerun: Show me the New York loans" }).click();
  await expect(page.getByText(/No AI model was called/)).toBeVisible();
  await expect(page.getByRole("table").last()).toBeVisible();
  expect(modelCalls).toEqual([]);
});
