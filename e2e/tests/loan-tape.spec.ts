/**
 * loan-tape.spec.ts: end-to-end tests of the Loan Tape screen.
 *
 * BUSINESS: protects what a visitor relies on: the synthetic-data warning, headline
 *   numbers and panels that match the API, desk-question chips whose counts equal
 *   what the grid then shows, a header count that follows the filter, sorting and
 *   filtering done on the server over the whole tape, delinquent loans in red,
 *   planned screens visibly disabled, and the explanation beside the grid.
 * TECH: elements are found by role and visible text (.claude/rules/e2e.md). The
 *   expected answers come from the API through Playwright's `request` fixture, so the
 *   tests hold for any seeded tape. Each test opens the page fresh.
 */
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const fmt = (n: number) => n.toLocaleString("en-US");

/** TECH: ask the API how many loans match a filter model. */
async function matching(request: APIRequestContext, filter?: object): Promise<number> {
  const params = new URLSearchParams({ limit: "1" });
  if (filter) params.set("filter", JSON.stringify(filter));
  const res = await request.get(`/api/loans?${params}`);
  expect(res.ok()).toBe(true);
  return (await res.json()).total;
}

/** TECH: open the Loan Tape and wait until the first block of loans is drawn. */
async function openTape(page: Page) {
  await page.goto("/");
  await expect(page.getByRole("columnheader", { name: "Loan ID" })).toBeVisible();
  await expect(page.getByTestId("row-count")).not.toHaveText("… loans");
}

test("shows the name, the synthetic data badge and the live sidebar", async ({ page }) => {
  await openTape(page);
  await expect(page.getByRole("heading", { name: "LoanIQ" })).toBeVisible();
  await expect(page.getByText("Synthetic data · demonstration only")).toBeVisible();
  await expect(page.getByRole("link", { name: "Loan Tape" })).toHaveAttribute("aria-current", "page");
});

test("planned screens and features are shown but cannot be used", async ({ page }) => {
  // BUSINESS: a visitor sees the whole workflow, and nothing pretends to work yet.
  await openTape(page);
  const nav = page.getByRole("navigation", { name: "Screens" });
  for (const label of ["Tape Upload", "Ask the Tape", "Slotting", "Best Execution", "Optimizer", "About"]) {
    const item = nav.locator("[aria-disabled='true']", { hasText: label });
    await expect(item).toContainText("Planned");
    await expect(nav.getByRole("link", { name: label })).toHaveCount(0);
  }
  await expect(page.getByRole("searchbox", { name: /Ask the tape/ })).toBeDisabled();
  await expect(page.getByRole("button", { name: /Export CSV/ })).toBeDisabled();
});

test("the panels and the tape line match the API", async ({ page, request }) => {
  // BUSINESS: every number on the panels comes from the real (synthetic) tape.
  const b = await (await request.get("/api/loans/breakdowns")).json();
  const t = await (await request.get("/api/tape")).json();
  await openTape(page);
  await expect(page.getByText(`Seller tape · ${t.fields} fields · ${t.sellers} fictional sellers`)).toBeVisible();

  const top = b.programs[0];
  const mix = page.getByRole("region", { name: "Program mix" });
  await expect(mix.getByRole("listitem").first()).toContainText(top.program);
  await expect(mix.getByRole("listitem").first()).toContainText((top.current_upb / 1e6).toFixed(1));

  const current = b.dq_status.find((s: { status: string }) => s.status === "Current");
  await expect(page.getByRole("region", { name: "MBA delinquency" })).toContainText(fmt(current.loans));
  await expect(page.getByRole("region", { name: "Note rate distribution" }).getByRole("listitem"))
    .toHaveCount(b.note_rates.length);
});

test("a desk-question chip filters the grid to exactly its count, and clears", async ({ page, request }) => {
  const counts = await (await request.get("/api/loans/questions")).json();
  const ltv = counts.find((c: { id: string }) => c.id === "ltv_over_125").loans;
  const all = await matching(request);
  await openTape(page);

  // BUSINESS: "LTV over 125" promises N loans; clicking it shows N loans, all above 125.
  const chip = page.getByRole("button", { name: /LTV over 125/ });
  await expect(chip).toContainText(fmt(ltv));
  const asked = page.waitForRequest((r) => r.url().includes("question=ltv_over_125"));
  await chip.click();
  await asked;
  await expect(chip).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByTestId("row-count")).toHaveText(`${fmt(ltv)} loans`);
  await expect(page.getByTestId("grid-showing")).toContainText(`${fmt(ltv)} of ${fmt(all)} loans`);

  await chip.click();
  await expect(chip).toHaveAttribute("aria-pressed", "false");
  await expect(page.getByTestId("row-count")).toHaveText(`${fmt(all)} loans`);
});

test("a chip and a column filter both apply", async ({ page, request }) => {
  // BUSINESS: "New York" AND "DQ status Current" is both at once, on the server.
  const res = await request.get(`/api/loans?limit=1&question=new_york&filter=${encodeURIComponent(
    JSON.stringify({ dq_status: { filterType: "text", type: "equals", filter: "Current" } }))}`);
  const expected = (await res.json()).total;
  await openTape(page);
  await page.getByRole("button", { name: /New York/ }).click();
  await page.getByRole("textbox", { name: "DQ Status Filter Input" }).fill("Current");
  // TECH: the floating filter box uses "contains"; "Current" matches only Current.
  await expect(page.getByTestId("row-count")).toHaveText(`${fmt(expected)} ${expected === 1 ? "loan" : "loans"}`);
});

test("Columns shows a field the grid hides by default", async ({ page }) => {
  // BUSINESS: the grid opens on the fields a trader reads first; the rest are one click away.
  await openTape(page);
  await expect(page.getByRole("columnheader", { name: "Servicer" })).toHaveCount(0);
  await page.getByRole("button", { name: /Columns/ }).click();
  await page.getByRole("checkbox", { name: "Servicer" }).check();
  await expect(page.getByRole("columnheader", { name: "Servicer" })).toBeVisible();
});

test("KPI tiles match the API summary", async ({ page, request }) => {
  // BUSINESS: the headline numbers a trader quotes equal the server's UPB-weighted ones.
  const s = await (await request.get("/api/loans/summary")).json();
  await openTape(page);
  await expect(page.getByRole("region", { name: "Loans", exact: true })).toContainText(fmt(s.loan_count));
  await expect(page.getByRole("region", { name: "WAC", exact: true })).toContainText(`${s.wac.toFixed(3)}%`);
  await expect(page.getByRole("region", { name: "WA LTV", exact: true })).toContainText(`${s.wa_ltv.toFixed(2)}%`);
  await expect(page.getByRole("region", { name: "Delinquent loans", exact: true })).toContainText(fmt(s.delinquent_loans));
});

test("header count shows the whole tape, then follows a filter", async ({ page, request }) => {
  const all = await matching(request);
  const ny = await matching(request, { state: { filterType: "text", type: "contains", filter: "NY" } });
  await openTape(page);
  await expect(page.getByTestId("row-count")).toHaveText(`${fmt(all)} loans`);

  // BUSINESS: "New York only", typed into the State column's filter box.
  await page.getByRole("textbox", { name: "State Filter Input" }).fill("NY");
  await expect(page.getByTestId("row-count")).toHaveText(`${fmt(ny)} ${ny === 1 ? "loan" : "loans"}`);
  expect(ny).toBeLessThan(all);
});

test("sorting is sent to the server and puts the largest balance first", async ({ page, request }) => {
  const top = (await (await request.get("/api/loans?limit=1&sort=current_upb:desc")).json()).rows[0];
  await openTape(page);
  const header = page.getByRole("columnheader", { name: "Current UPB ($)" });

  // TECH: AG Grid cycles ascending -> descending; each click asks the server again.
  await header.click();
  await expect(header).toHaveAttribute("aria-sort", "ascending");
  const sorted = page.waitForRequest((r) => r.url().includes("sort=current_upb%3Adesc"));
  await header.click();
  await sorted;
  await expect(header).toHaveAttribute("aria-sort", "descending");
  await expect(page.getByRole("gridcell", { name: top.loan_id })).toBeVisible();
});

test("delinquent status shows in red, Current does not", async ({ page }) => {
  await openTape(page);
  const red = "rgb(255, 107, 107)";
  await page.getByRole("textbox", { name: "DQ Status Filter Input" }).fill("REO");
  await expect(page.getByRole("gridcell", { name: "REO", exact: true }).first()).toHaveCSS("color", red);

  await page.getByRole("textbox", { name: "DQ Status Filter Input" }).fill("Current");
  const current = page.getByRole("gridcell", { name: "Current", exact: true }).first();
  await expect(current).toBeVisible();
  await expect(current).not.toHaveCSS("color", red);
});

test("numbers are formatted for the desk", async ({ page, request }) => {
  // BUSINESS: money with commas and no cents, rates to 3 decimals.
  const first = (await (await request.get("/api/loans?limit=1")).json()).rows[0];
  await openTape(page);
  const upb = Math.round(first.current_upb).toLocaleString("en-US");
  await expect(page.getByRole("gridcell", { name: upb, exact: true }).first()).toBeVisible();
  await expect(page.getByRole("gridcell", { name: first.note_rate.toFixed(3), exact: true }).first()).toBeVisible();
});

test("the explain panel shows the Business and Technical explanation", async ({ page }) => {
  // BUSINESS: the explanation is open beside the grid on first visit, as in the design.
  await openTape(page);
  const panel = page.getByRole("complementary", { name: "Screen explanation" });
  await expect(panel.getByRole("tab", { name: "Business" })).toHaveAttribute("aria-selected", "true");
  await expect(panel.getByRole("tabpanel")).toContainText("first look at a pool of loans");
  await panel.getByRole("tab", { name: "Technical" }).click();
  await expect(panel.getByRole("tabpanel")).toContainText("parameterized SQL");

  await page.getByRole("button", { name: "Hide explanation" }).click();
  await expect(panel).toHaveCount(0);
  await page.getByRole("button", { name: "Explain this screen" }).click();
  await expect(page.getByRole("complementary", { name: "Screen explanation" })).toBeVisible();
});

test("a screen URL reloads into the app, and unknown API URLs stay JSON 404s", async ({ page, request }) => {
  await page.goto("/some/screen");
  await expect(page.getByRole("heading", { name: "LoanIQ" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Screen not found" })).toBeVisible();
  await page.getByRole("link", { name: "Go to the Loan Tape" }).click();
  await expect(page.getByRole("columnheader", { name: "Loan ID" })).toBeVisible();
  const res = await request.get("/api/does-not-exist");
  expect(res.status()).toBe(404);
});
