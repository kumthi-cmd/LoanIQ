/**
 * ask/conversation.ts: one question and its answer ("a turn"), built from stream events.
 *
 * Where it sits: askStream.ts events -> [conversation: applyEvent] -> AnswerTurn
 * component; saved-query reruns -> [rerunTurn] -> AnswerTurn.
 *
 * BUSINESS: a turn is what the visitor sees for one question: the question, each
 *   tool the agent called (with its SQL and result count), the answer, any notice
 *   that built-in rules answered, and the result tables to open or save.
 * TECH: plain functions that return a NEW turn object instead of changing the old
 *   one. React redraws when state is replaced, not when an object inside it is
 *   changed in place, so this "immutable update" style is what makes the screen
 *   follow the stream. Each function is easy to unit test without React.
 */
import type { StoredQuery } from "../api/types";
import type { AnswerEvent, AskEvent, DoneEvent, ToolResultEvent } from "./askStream";

/**
 * One tool call as the screen shows it: the call, then (once it ran) its result.
 * TECH: result is undefined while the tool is running.
 */
export interface ToolStep {
  id: string;
  name: string;
  input: Record<string, unknown>;
  result?: ToolResultEvent;
}

/**
 * One question and everything shown under it.
 * TECH: status "running" while the stream is open; "error" when it failed before an
 *   answer (error holds the message). rerun marks a saved query rerun (no model).
 *   fallbackNotice is set when built-in rules took over mid-question.
 */
export interface Turn {
  id: string;
  question: string;
  status: "running" | "done" | "error";
  steps: ToolStep[];
  answer?: AnswerEvent;
  done?: DoneEvent;
  fallbackNotice?: string;
  error?: string;
  rerun?: boolean;
  /** TECH: full results already in hand (reruns), by query id, so no refetch is needed. */
  results?: Record<string, StoredQuery>;
}

/** A new turn for a question that is about to be sent. */
export function newTurn(id: string, question: string): Turn {
  return { id, question, status: "running", steps: [] };
}

/**
 * Apply one stream event to a turn, returning the updated turn.
 * BUSINESS: tool chips appear as the agent calls tools; the answer when it is ready.
 * TECH: a tool_result is matched to its call by id. Call ids are unique only within
 *   one model reply ("c1", "c2" ... again in the next round), so the match is the
 *   LAST call with that id that has no result yet. "escalated" changes nothing on
 *   screen.
 */
export function applyEvent(turn: Turn, event: AskEvent): Turn {
  switch (event.type) {
    case "tool_call":
      return { ...turn, steps: [...turn.steps, { ...event.data }] };
    case "tool_result": {
      const index = lastOpenStep(turn.steps, event.data.id);
      if (index === -1) return turn;
      const steps = turn.steps.map((s, i) => (i === index ? { ...s, result: event.data } : s));
      return { ...turn, steps };
    }
    case "fallback":
      return { ...turn, fallbackNotice: event.data.notice };
    case "answer":
      return { ...turn, answer: event.data };
    case "done":
      return { ...turn, done: event.data, status: "done" };
    default:
      return turn;
  }
}

/** TECH: index of the last step with this call id still waiting for its result, or -1. */
function lastOpenStep(steps: ToolStep[], id: string): number {
  for (let i = steps.length - 1; i >= 0; i -= 1) {
    if (steps[i].id === id && !steps[i].result) return i;
  }
  return -1;
}

/** Mark a turn failed. BUSINESS: the screen says what went wrong instead of spinning. */
export function failTurn(turn: Turn, message: string): Turn {
  return { ...turn, status: "error", error: message };
}

/**
 * The query results a turn shows as tables, in the order the agent ran them.
 * BUSINESS: only queries that ran; a refused query has no rows to show.
 */
export function resultSteps(turn: Turn): (ToolStep & { result: ToolResultEvent & { query_id: string } })[] {
  return turn.steps.filter(
    (s): s is ToolStep & { result: ToolResultEvent & { query_id: string } } =>
      s.result?.status === "ok" && typeof s.result.query_id === "string",
  );
}

/**
 * A turn for a saved query rerun: one query_tape step per stored result.
 * BUSINESS: looks like an answer, says plainly that no model was called.
 * TECH: answer text is the content/ note; provider "saved" so no fallback notice.
 */
export function rerunTurn(id: string, tag: string, results: StoredQuery[], note: string): Turn {
  const steps: ToolStep[] = results.map((q, i) => ({
    id: `r${i + 1}`,
    name: "query_tape",
    input: { sql: q.sql, title: q.title },
    result: {
      id: `r${i + 1}`, name: "query_tape", status: "ok", sql: q.sql, title: q.title,
      query_id: q.query_id, row_count: q.row_count, total_rows: q.total_rows,
      truncated: q.truncated, loan_tape: q.loan_tape ?? null,
    },
  }));
  return {
    id, question: tag, status: "done", steps, rerun: true,
    answer: { text: note, provider: "saved", model: "none", notice: null },
    results: Object.fromEntries(results.map((q) => [q.query_id, q])),
  };
}
