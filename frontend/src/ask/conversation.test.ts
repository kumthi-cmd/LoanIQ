/**
 * Tests for ask/conversation.ts: building one turn from the stream.
 *
 * BUSINESS: protects what the visitor sees under a question: each tool call paired
 *   with its own result, the notice when built-in rules took over, only queries
 *   that ran as tables, and a saved-query rerun that says no model was called.
 * TECH: pure functions, no React.
 */
import { describe, expect, it } from "vitest";
import type { StoredQuery } from "../api/types";
import type { AskEvent } from "./askStream";
import { applyEvent, failTurn, newTurn, rerunTurn, resultSteps } from "./conversation";

const call = (id: string, name = "query_tape"): AskEvent => ({ type: "tool_call", data: { id, name, input: {} } });
const ok = (id: string, queryId?: string): AskEvent => ({
  type: "tool_result", data: { id, name: "query_tape", status: "ok", query_id: queryId, sql: "SELECT 1" },
});

describe("applyEvent", () => {
  it("pairs each result with its call, even when call ids repeat across rounds", () => {
    // TECH: Claude numbers calls per reply, so round 2 can reuse "c1".
    const events: AskEvent[] = [call("c1"), ok("c1", "q_1"), call("c1"), ok("c1", "q_2")];
    const turn = events.reduce(applyEvent, newTurn("t1", "q"));
    expect(turn.steps.map((s) => s.result?.query_id)).toEqual(["q_1", "q_2"]);
  });

  it("keeps the fallback notice, the answer and the done summary", () => {
    const turn = [
      { type: "fallback", data: { reason: "timeout", notice: "Answered by built-in rules" } },
      { type: "answer", data: { text: "20 loans", provider: "offline", model: "offline", notice: "Answered by built-in rules" } },
      { type: "done", data: { provider: "offline", rounds: 1, cost_usd: "0", fallback_reason: "timeout", query_ids: [], elapsed_ms: 5 } },
    ].reduce((t, e) => applyEvent(t, e as AskEvent), newTurn("t1", "q"));
    expect(turn.fallbackNotice).toBe("Answered by built-in rules");
    expect(turn.answer?.text).toBe("20 loans");
    expect(turn.status).toBe("done");
  });

  it("ignores a result with no matching call and leaves the old turn unchanged", () => {
    const before = newTurn("t1", "q");
    const after = applyEvent(before, ok("c9"));
    expect(after).toBe(before);
    expect(applyEvent(before, call("c1"))).not.toBe(before); // TECH: a new object, React redraws
    expect(before.steps).toEqual([]);
  });
});

describe("resultSteps", () => {
  it("lists only queries that ran, in order", () => {
    const refused: AskEvent = { type: "tool_result", data: { id: "c2", name: "query_tape", status: "rejected", reason: "Unknown column" } };
    const turn = [call("c1"), ok("c1", "q_1"), call("c2"), refused, call("c3", "lookup_term"), ok("c3")]
      .reduce(applyEvent, newTurn("t1", "q"));
    expect(resultSteps(turn).map((s) => s.result.query_id)).toEqual(["q_1"]);
  });
});

describe("rerunTurn and failTurn", () => {
  it("builds a finished turn from stored results, saying no model was called", () => {
    const q = { query_id: "q_9", title: "LTV > 125", sql: "SELECT 1", columns: [], rows: [], row_count: 20,
      total_rows: 20, truncated: false, loan_tape: null, added_columns: [] } as StoredQuery;
    const turn = rerunTurn("t2", "Every loan over 125 LTV", [q], "No AI model was called.");
    expect(turn).toMatchObject({ status: "done", rerun: true, question: "Every loan over 125 LTV" });
    expect(turn.answer?.text).toBe("No AI model was called.");
    expect(resultSteps(turn)[0].result.query_id).toBe("q_9");
    expect(turn.results?.q_9).toBe(q);
  });

  it("marks a turn failed with its message", () => {
    expect(failTurn(newTurn("t1", "q"), "offline")).toMatchObject({ status: "error", error: "offline" });
  });
});
