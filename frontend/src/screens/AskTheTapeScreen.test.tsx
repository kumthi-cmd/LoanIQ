/**
 * Tests for the Ask the Tape screen (Step 4b), inside the real app frame and routes.
 *
 * BUSINESS: protects the desk's whole loop on this screen:
 *   - ask a question and watch the tool chips, the answer and the rows arrive;
 *   - click a tool chip to see the SQL it ran;
 *   - click a loan ID to see the whole loan;
 *   - open the same filter in the Loan Tape, or see why it cannot open;
 *   - save a query and rerun it WITHOUT calling the model;
 *   - see the Offline banner when built-in rules answer, and a clear error;
 *   - open the agent explainer from the Agent mark beside the title (Step 4d).
 * TECH: the real routes in a memory router; fetch is mocked per URL and method. The
 *   question stream is a real Response with an SSE body. LoanGrid is stubbed (AG Grid
 *   needs real layout); it prints the filter it was given.
 */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RouterProvider, createMemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { routes } from "../App";
import { STORAGE_KEY } from "../ask/savedQueries";

vi.mock("../components/LoanGrid", () => ({
  LoanGrid: ({ initialFilter }: { initialFilter?: Record<string, unknown> | null }) => (
    <div>grid filter: {initialFilter ? JSON.stringify(initialFilter) : "none"}</div>
  ),
}));

const COLUMNS = [
  { name: "loan_id", type: "VARCHAR", kind: "text", label: "Loan ID" },
  { name: "ltv", type: "DECIMAL(6,2)", kind: "number", label: "LTV (%)" },
  { name: "current_upb", type: "DECIMAL(14,2)", kind: "number", label: "Current UPB ($)" },
];
const LINK = { filter: { ltv: { filterType: "number", type: "greaterThan", filter: 125 } }, sort: "ltv:desc", reason: null };
const SQL = "SELECT loan_id, ltv, current_upb\nFROM loans\nWHERE ltv > 125\nORDER BY ltv DESC";
const stored = (id: string, link: unknown = LINK) => ({
  query_id: id, title: "LTV over 125", sql: SQL, columns: ["loan_id", "ltv", "current_upb"],
  rows: [["LN00000001", 130.5, 250000.4], ["LN00000002", 127, 99000]],
  row_count: 2, total_rows: 2, truncated: false, loan_tape: link,
});

/** The SSE body of one answered question with one query. */
function sseAnswer(link: unknown = LINK): string {
  const ev = (type: string, data: unknown) => `event: ${type}\ndata: ${JSON.stringify(data)}\n\n`;
  return [
    ev("tool_call", { id: "c1", name: "query_tape", input: { sql: SQL, title: "LTV over 125" } }),
    ev("tool_result", { id: "c1", name: "query_tape", status: "ok", sql: SQL, title: "LTV over 125",
      query_id: "q_1", row_count: 2, total_rows: 2, truncated: false, loan_tape: link }),
    ev("answer", { text: "**2 loans** are over 125 LTV; the highest is LN00000001.", provider: "anthropic", model: "m", notice: null }),
    ev("done", { provider: "anthropic", rounds: 2, cost_usd: "0.001000", fallback_reason: null, query_ids: ["q_1"], elapsed_ms: 900 }),
  ].join("");
}

let status: unknown = { mode: "model", reason: null, notice: null };
let askBody = sseAnswer();
let askStatusCode = 200;
let link: unknown = LINK;

const json = (body: unknown, code = 200) => Promise.resolve(new Response(JSON.stringify(body), { status: code }));
const fetchMock = vi.fn((url: string, init?: RequestInit) => {
  if (url === "/api/ask" && init?.method === "POST") {
    if (askStatusCode !== 200) return json({ detail: "Ask a question about the loan tape." }, askStatusCode);
    return Promise.resolve(new Response(askBody, { status: 200, headers: { "Content-Type": "text/event-stream" } }));
  }
  if (url === "/api/ask/rerun") return json(stored("q_2", link));
  if (url === "/api/ask/status") return json(status);
  if (url.startsWith("/api/ask/queries/")) return json(stored("q_1", link));
  if (url === "/api/ask/loans/LN00000001") {
    return json({ loan_id: "LN00000001", loan: { loan_id: "LN00000001", ltv: 130.5, current_upb: 250000.4 } });
  }
  if (url === "/api/loans/columns") return json(COLUMNS);
  return json({ detail: "not found" }, 404);
});

beforeEach(() => {
  status = { mode: "model", reason: null, notice: null };
  askBody = sseAnswer();
  askStatusCode = 200;
  link = LINK;
  fetchMock.mockClear();
  window.localStorage.clear();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

const renderAsk = () => {
  const router = createMemoryRouter(routes, { initialEntries: ["/ask"] });
  render(<RouterProvider router={router} />);
  return router;
};
const modelCalls = () => fetchMock.mock.calls.filter(([u, i]) => u === "/api/ask" && i?.method === "POST").length;

/** Type a question, send it, and wait for its rows. */
async function askLtv() {
  await userEvent.type(screen.getByRole("textbox", { name: "Ask the tape" }), "Loans over 125 LTV?");
  await userEvent.click(screen.getByRole("button", { name: "Send question" }));
  return screen.findByRole("table");
}

describe("Ask the Tape", () => {
  it("streams the tool chips, the answer and the rows behind it", async () => {
    renderAsk();
    expect(screen.getByRole("heading", { name: "Ask the Tape" })).toBeInTheDocument();
    const table = await askLtv();
    expect(screen.getByText("Loans over 125 LTV?")).toHaveClass("question-bubble");
    expect(screen.getByRole("button", { name: "query_tape → 2 rows" })).toBeInTheDocument();
    expect(screen.getByText("2 loans").tagName).toBe("STRONG");
    // BUSINESS: rows formatted like the Loan Tape: LTV 2 decimals, money with commas.
    const cells = within(table).getAllByRole("cell").map((c) => c.textContent);
    expect(cells.slice(0, 3)).toEqual(["LN00000001", "130.50", "250,000"]);
    expect(within(table).getByRole("columnheader", { name: "LTV (%)" })).toBeInTheDocument();
    expect(screen.getByText("2 of 2 rows shown")).toBeInTheDocument();
    expect(modelCalls()).toBe(1);
  });

  it("shows the SQL a tool chip ran, and hides it again", async () => {
    renderAsk();
    await askLtv();
    const chip = screen.getByRole("button", { name: "query_tape → 2 rows" });
    await userEvent.click(chip);
    expect(chip).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByTestId("tool-detail")).toHaveTextContent("WHERE ltv > 125");
    await userEvent.click(chip);
    expect(screen.queryByTestId("tool-detail")).not.toBeInTheDocument();
  });

  it("opens the loan drawer from a loan ID in the answer, with every field, and closes on Escape", async () => {
    renderAsk();
    await askLtv();
    // TECH: the ID appears in the answer text and in the table; the first is the answer's.
    await userEvent.click(screen.getAllByRole("button", { name: "LN00000001" })[0]);
    const drawer = await screen.findByRole("dialog", { name: "Loan LN00000001" });
    expect(await within(drawer).findByText("LTV (%)")).toBeInTheDocument();
    expect(within(drawer).getByText("130.50")).toBeInTheDocument();
    expect(within(drawer).getByText("250,000")).toBeInTheDocument();
    expect(within(drawer).getByRole("button", { name: "Close" })).toHaveFocus();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("opens the same filter in the Loan Tape, and has no Send to Slotting yet", async () => {
    const router = renderAsk();
    await askLtv();
    expect(screen.queryByText(/Send .* to Slotting/)).not.toBeInTheDocument();
    const open = screen.getByRole("link", { name: "Open in Loan Tape" });
    expect(open.getAttribute("href")).toBe(`/?filter=${encodeURIComponent(JSON.stringify(LINK.filter))}&sort=ltv%3Adesc`);
    await userEvent.click(open);
    expect(router.state.location.pathname).toBe("/");
    expect(await screen.findByText(`grid filter: ${JSON.stringify(LINK.filter)}`)).toBeInTheDocument();
  });

  it("says why an answer cannot open in the Loan Tape", async () => {
    link = { filter: null, sort: null, reason: "The filter uses OR across conditions." };
    askBody = sseAnswer(link);
    renderAsk();
    await askLtv();
    expect(screen.getByRole("button", { name: "Open in Loan Tape" })).toBeDisabled();
    expect(screen.getByText(/Can't open in the Loan Tape: The filter uses OR/)).toBeInTheDocument();
  });

  it("saves a query and reruns its SQL without calling the model", async () => {
    renderAsk();
    await askLtv();
    await userEvent.click(screen.getByRole("button", { name: "Save query" }));
    expect(screen.getByText("Saved as")).toBeInTheDocument();
    expect(JSON.parse(window.localStorage.getItem(STORAGE_KEY)!)[0].queries[0].sql).toBe(SQL);
    await userEvent.click(screen.getByRole("button", { name: "Rerun: Loans over 125 LTV?" }));
    expect(await screen.findByText(/No AI model was called/)).toBeInTheDocument();
    const rerun = fetchMock.mock.calls.find(([u]) => u === "/api/ask/rerun");
    expect(JSON.parse(String(rerun![1]!.body))).toEqual({ sql: SQL, title: "LTV over 125" });
    expect(modelCalls()).toBe(1); // BUSINESS: still just the first question
    expect(screen.getAllByRole("table")).toHaveLength(2);
  });

  it("lists queries saved earlier in this browser", async () => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify([{ tag: "PR · all", question: "Puerto Rico loans", queries: [{ sql: "SELECT 1", title: "PR" }] }]));
    renderAsk();
    expect(screen.getByRole("button", { name: "Rerun: Puerto Rico loans" })).toHaveTextContent("PR · all");
  });

  it("shows the Offline banner when built-in rules are answering", async () => {
    status = { mode: "offline", reason: "unavailable", notice: "Answered by built-in rules: the AI model is switched off on this server." };
    renderAsk();
    const banner = await screen.findByRole("status");
    expect(banner).toHaveTextContent("Offline is answering");
    expect(banner).toHaveTextContent("switched off on this server");
  });

  it("shows no banner while the model answers", async () => {
    renderAsk();
    await askLtv();
    expect(screen.queryByText("Offline is answering")).not.toBeInTheDocument();
  });

  it("shows the server's reason when a question is refused", async () => {
    askStatusCode = 400;
    renderAsk();
    await userEvent.type(screen.getByRole("textbox", { name: "Ask the tape" }), "x");
    await userEvent.keyboard("{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not get an answer: Ask a question about the loan tape.");
  });

  it("starts a new thread", async () => {
    renderAsk();
    await askLtv();
    await userEvent.click(screen.getByRole("button", { name: "New thread" }));
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.getByText(/Ask a question about the tape, or pick one below/)).toBeInTheDocument();
  });

  it("explains itself, with the agent's tools and guardrails always shown", async () => {
    renderAsk();
    const tools = screen.getByRole("region", { name: "Tools the agent can call" });
    for (const name of ["list_columns", "query_tape", "summarize_tape", "lookup_term", "get_loan"]) {
      expect(within(tools).getByText(name)).toBeInTheDocument();
    }
    await userEvent.click(screen.getByRole("button", { name: "Explain this screen" }));
    const panel = screen.getByRole("complementary", { name: "Screen explanation" });
    expect(panel).toHaveTextContent("A trader asks the tape");
  });

  // BUSINESS: the Agent mark beside the title explains the agent behind this screen:
  //   content/agent.md and the loop diagram. Esc closes it and the keyboard user is
  //   back on the mark, ready to carry on.
  it("opens the agent explainer from the title's mark, and Esc closes it and returns focus", async () => {
    renderAsk();
    const heading = screen.getByRole("heading", { level: 2, name: "Ask the Tape" });
    const mark = within(heading.parentElement!).getByRole("button", { name: /^Agent/ });
    // TECH: Enter on a focused button clicks it, so the keyboard path is the real one.
    mark.focus();
    await userEvent.keyboard("{Enter}");
    const dialog = screen.getByRole("dialog", { name: "The Ask the Tape agent" });
    expect(dialog).toHaveFocus();
    expect(within(dialog).getByText(/Ask the Tape uses one Claude agent/)).toBeInTheDocument();
    const diagram = within(dialog).getByRole("img", { name: /The Ask the Tape agent loop/ });
    expect(diagram.tagName).toBe("IMG");
    expect(diagram).toHaveAttribute("src", expect.stringContaining("ask-the-tape-agent"));
    // BUSINESS: no model call is made by opening the explainer.
    expect(modelCalls()).toBe(0);
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(mark).toHaveFocus();
    expect(mark).toHaveAttribute("aria-expanded", "false");
  });

  it("closes the agent explainer with its Close button, and a second click on the mark toggles it", async () => {
    renderAsk();
    const heading = screen.getByRole("heading", { level: 2, name: "Ask the Tape" });
    const mark = within(heading.parentElement!).getByRole("button", { name: /^Agent/ });
    await userEvent.click(mark);
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(mark).toHaveFocus();
    // TECH: a press on the mark is not an "outside click", so it opens, then closes.
    await userEvent.click(mark);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await userEvent.click(mark);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
