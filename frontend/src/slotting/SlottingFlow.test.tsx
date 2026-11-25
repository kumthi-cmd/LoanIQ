/**
 * Tests for the Product Slotting flow across the app: sidebar action, run dialog,
 * Slotting panel, notice and the Loan Tape's reload (Step 5b).
 *
 * BUSINESS: the "5 · Product Slotting" board, end to end in the app:
 *   - before a run the sidebar says "Not run on this tape" and the panel offers a run;
 *   - the confirm dialog shows the tape and the rules from the API, and Escape or
 *     Cancel leaves everything as it was;
 *   - the commentary appears one line at a time, never all at once, then the totals;
 *   - the dialog closes by itself (or with Go now), lands on the Loan Tape, shows the
 *     notice, and the grid's columns are fetched again with Slot and Spec Stories;
 *   - a run already going (HTTP 409) shows the server's reason;
 *   - after someone else's run, the confirm warns that it will be replaced.
 * TECH: the real routes in a memory router, fetch mocked per URL, the run's stream a
 *   real ReadableStream. LoanGrid is a stub (AG Grid needs real layout; Playwright
 *   covers it). Fake timers drive the pacing; shouldAdvanceTime keeps Testing
 *   Library's own waiting working.
 */
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { routes } from "../App";
import type { SlottingStatus } from "../api/types";
import { slottingConfig } from "./slottingConfig";
import { NOT_RUN, RUN, STEPS, streamText } from "./slottingFixtures";

vi.mock("../components/LoanGrid", () => ({
  LoanGrid: ({ columns, onLoanHover }: { columns: { name: string }[]; onLoanHover?: unknown }) => (
    <div>
      <span>grid columns: {columns.map((c) => c.name).join(",")}</span>
      <span>grid hover: {onLoanHover ? "on" : "off"}</span>
    </div>
  ),
}));

const TAPE = { loans: 2000, fields: 41, sellers: 6 };
const BASE_COLUMNS = [{ name: "loan_id", type: "VARCHAR", kind: "text", label: "Loan ID", default_visible: true }];
const SLOT_COLUMNS = [...BASE_COLUMNS,
  { name: "slot", type: "VARCHAR", kind: "text", label: "Slot", default_visible: true },
  { name: "spec_stories", type: "VARCHAR", kind: "text", label: "Spec Stories", default_visible: true }];

let status: SlottingStatus;
let runResponse: () => Response;

const json = (body: unknown, code = 200) => new Response(JSON.stringify(body), { status: code });

function streamResponse(text: string): Response {
  const body = new ReadableStream<Uint8Array>({
    start(ctrl) {
      ctrl.enqueue(new TextEncoder().encode(text));
      ctrl.close();
    },
  });
  return new Response(body, { status: 200 });
}

// TECH: the mock answers by URL, like the real API; anything else is a 404.
function answer(url: string): Response {
  if (url === "/api/slotting/run") return runResponse();
  if (url.includes("/api/slotting/status")) return json(status);
  if (url.includes("/api/loans/columns")) return json(status.run ? SLOT_COLUMNS : BASE_COLUMNS);
  if (url.includes("/api/tape")) return json(TAPE);
  if (url.includes("/api/loans/summary")) return json({ loan_count: 2000, total_current_upb: 6e8, wac: 6, wa_fico: 740, wa_ltv: 75, delinquent_loans: 1 });
  if (url.includes("/api/loans/breakdowns")) return json({ programs: [], note_rates: [], dq_status: [] });
  if (url.includes("/api/loans/questions")) return json([]);
  return json({ detail: "not found" }, 404);
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  status = NOT_RUN;
  runResponse = () => {
    status = RUN; // BUSINESS: the server publishes as the run finishes.
    // TECH: as the real server does, the done event says running: true (it is sent
    //   while the run lock is still held); the screen must not keep saying "Running…".
    return streamResponse(streamText(STEPS, { ...RUN, running: true }));
  };
  vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(answer(String(url)))));
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

const renderApp = (path = "/") => {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(<RouterProvider router={router} />);
  return router;
};
// TECH: inside the sidebar, since the Slotting panel has its own "Run Product Slotting".
const sidebarAction = () =>
  within(screen.getByRole("navigation", { name: "Screens" })).getByRole("button", { name: /Product Slotting/ });
const columnFetches = () => vi.mocked(fetch).mock.calls.filter(([u]) => String(u).includes("/api/loans/columns")).length;
const advance = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });

describe("Product Slotting flow", () => {
  it("before a run: the sidebar and the panel say so, and the grid has no hover cards", async () => {
    renderApp();
    await waitFor(() => expect(sidebarAction()).toHaveTextContent("Not run on this tape"));
    const panel = screen.getByRole("region", { name: "Slotting" });
    expect(within(panel).getByRole("button", { name: "Run Product Slotting" })).toBeInTheDocument();
    expect(await screen.findByText("grid hover: off")).toBeInTheDocument();
  });

  it("the confirm dialog shows the tape and the rules, and Escape leaves it", async () => {
    renderApp();
    await waitFor(() => expect(sidebarAction()).toHaveTextContent("Not run"));
    fireEvent.click(sidebarAction());
    const dialog = await screen.findByRole("dialog", { name: "Run Product Slotting?" });
    expect(await within(dialog).findByText("2,000 loans · 41 fields")).toBeInTheDocument();
    expect(within(dialog).getByText(/12 rules in 4 spec stories: LLB tiers \$85K to \$275K, NY, PR, Low FICO/))
      .toBeInTheDocument();
    expect(within(dialog).queryByText(/This replaces/)).toBeNull();
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(vi.mocked(fetch).mock.calls.some(([u]) => String(u) === "/api/slotting/run")).toBe(false);
  });

  it("shows the commentary one line at a time, then the totals, then updates the Loan Tape", async () => {
    renderApp();
    await screen.findByText("grid columns: loan_id");
    fireEvent.click(within(screen.getByRole("region", { name: "Slotting" })).getByRole("button", { name: "Run Product Slotting" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Run slotting" }));
    await screen.findByRole("heading", { name: "Slotting the tape" });

    // BUSINESS: all steps have arrived, but only the paced lines are shown.
    const lines = () => within(screen.getByRole("dialog")).queryAllByRole("listitem")
      .filter((li) => !li.textContent?.endsWith("…"));
    expect(lines()).toHaveLength(0);
    await advance(slottingConfig.stepMs);
    expect(lines().map((l) => l.textContent)).toEqual([STEPS[0].line]);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", String(STEPS[0].percent));
    expect(screen.getByText(`Step 2 of 3 · ${STEPS[1].name}`)).toBeInTheDocument();
    await advance(slottingConfig.stepMs * 2);

    // BUSINESS: done: the totals from the done event.
    expect(screen.getByRole("heading", { name: "Loan Tape updated" })).toBeInTheDocument();
    expect(screen.getByText("1,467 of 2,000 loans slotted: 1,104 with a spec story, 363 generic TBA.")).toBeInTheDocument();
    const before = columnFetches();

    // BUSINESS: the dialog closes by itself, the notice appears, the columns reload.
    await advance(slottingConfig.doneHoldMs);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent("Loan Tape updated by Product Slotting");
    expect(screen.getByRole("status")).toHaveTextContent("1,467 of 2,000 loans slotted");
    await screen.findByText("grid columns: loan_id,slot,spec_stories");
    expect(columnFetches()).toBeGreaterThan(before);
    expect(screen.getByText("grid hover: on")).toBeInTheDocument();
    expect(sidebarAction()).toHaveTextContent(/Last run \d{1,2}:\d{2} (AM|PM)/);
    expect(within(screen.getByRole("region", { name: "Slotting" })).getByText("LLB tiers")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Close message" }));
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("Go now skips the wait, and a run started elsewhere ends on the Loan Tape", async () => {
    const router = renderApp("/about");
    await waitFor(() => expect(sidebarAction()).toHaveTextContent("Not run"));
    fireEvent.click(sidebarAction());
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Run slotting" }));
    await advance(slottingConfig.stepMs * STEPS.length);
    fireEvent.click(await screen.findByRole("button", { name: "Go now" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(router.state.location.pathname).toBe("/");
    expect(await screen.findByRole("status")).toHaveTextContent("Loan Tape updated");
    // BUSINESS: the run is over: the sidebar gives its time, not "Running…".
    expect(sidebarAction()).toHaveTextContent(/Last run/);
    expect(sidebarAction()).not.toHaveTextContent("Running");
  });

  it("a run already going shows the server's reason, and Close leaves the tape as it was", async () => {
    runResponse = () => json({ detail: "Product Slotting is already running on this tape." }, 409);
    renderApp();
    await waitFor(() => expect(sidebarAction()).toHaveTextContent("Not run"));
    fireEvent.click(sidebarAction());
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Run slotting" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("already running");
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("after an earlier run, the tape opens slotted and the confirm warns it will be replaced", async () => {
    status = RUN;
    renderApp();
    await screen.findByText("grid columns: loan_id,slot,spec_stories");
    await waitFor(() => expect(sidebarAction()).toHaveTextContent("Last run"));
    fireEvent.click(sidebarAction());
    expect(await screen.findByText(/This replaces the slotting from \d{1,2}:\d{2} (AM|PM)\./)).toBeInTheDocument();
  });
});
