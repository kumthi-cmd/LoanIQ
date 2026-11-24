/**
 * ask/askStream.ts: send one question to POST /api/ask and read the answer as it streams.
 *
 * Where it sits: Ask the Tape screen -> [askStream] -> POST /api/ask (Server-Sent
 * Events) -> each event -> ask/conversation.ts (builds the turn on screen).
 *
 * BUSINESS: the visitor watches the agent work: each tool call (with its SQL)
 *   appears as it happens, then the answer, then what it cost. Nothing waits for
 *   the whole answer to finish.
 * TECH:
 *   - Server-Sent Events (SSE) are blocks of "event: <type>" and "data: <json>"
 *     lines, separated by a blank line. The browser's own EventSource can only make
 *     GET requests, and the question is a POST body, so this module uses fetch()
 *     and reads the response body as a stream of bytes (ReadableStream), decoding
 *     and splitting it into events itself.
 *   - A network chunk can end in the middle of an event, so the text is buffered
 *     and only complete blocks (ending in a blank line) are parsed.
 *   - A bad request (empty or overlong question) is a normal HTTP 400 before any
 *     stream starts (backend/app/agent/api.py), so it becomes an ApiError.
 *   - The event shapes are written here by hand: OpenAPI describes JSON responses,
 *     not the events inside a stream. They mirror backend/app/agent/orchestrator.py
 *     (Event) and tools.py (tool_result fields); the e2e tests run them end to end.
 */
import { readJson } from "../api/client";
import type { AskRequest, LoanTapeLink } from "../api/types";

/** BUSINESS: the model asked LoanIQ to run a tool. */
export interface ToolCallEvent {
  id: string;
  name: string;
  input: Record<string, unknown>;
}

/**
 * BUSINESS: what the tool did. status "rejected" means a guardrail refused the call.
 * TECH: sql, title, query_id, row_count, total_rows, truncated and loan_tape come
 *   with query_tape; sql alone with summarize_tape; loan_id with get_loan.
 */
export interface ToolResultEvent {
  id: string;
  name: string;
  status: "ok" | "rejected" | "failed";
  reason?: string;
  sql?: string;
  title?: string;
  query_id?: string;
  row_count?: number;
  total_rows?: number;
  truncated?: boolean;
  loan_tape?: LoanTapeLink | null;
  loan_id?: string;
}

/** BUSINESS: built-in rules took over, and why. */
export interface FallbackEvent {
  reason: string;
  notice: string;
}

/** BUSINESS: the answer, who wrote it, and a notice if built-in rules did. */
export interface AnswerEvent {
  text: string;
  provider: string;
  model: string;
  notice: string | null;
}

/** BUSINESS: the question's cost and work. TECH: cost_usd is a string with 6 decimals. */
export interface DoneEvent {
  provider: string;
  rounds: number;
  cost_usd: string;
  fallback_reason: string | null;
  query_ids: string[];
  elapsed_ms: number;
}

/** One event from the stream, typed by its name. */
export type AskEvent =
  | { type: "tool_call"; data: ToolCallEvent }
  | { type: "tool_result"; data: ToolResultEvent }
  | { type: "escalated"; data: { model: string; guardrail_failures: number } }
  | { type: "fallback"; data: FallbackEvent }
  | { type: "answer"; data: AnswerEvent }
  | { type: "done"; data: DoneEvent };

/**
 * Parse one SSE block into an event, or null for a comment or keep-alive.
 * TECH: "event:" names it; one or more "data:" lines hold the JSON (joined with
 *   newlines, as the SSE standard says). Lines starting ":" are comments. A block
 *   with no event name is SSE's default "message" type, which /api/ask never sends.
 */
export function parseSseBlock(block: string): AskEvent | null {
  let type = "";
  const data: string[] = [];
  for (const line of block.split(/\r?\n/)) {
    if (!line || line.startsWith(":")) continue;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    // TECH: one optional space after the colon is part of the format, not the value.
    const value = colon === -1 ? "" : line.slice(colon + 1).replace(/^ /, "");
    if (field === "event") type = value;
    else if (field === "data") data.push(value);
  }
  if (!type || data.length === 0) return null;
  return { type, data: JSON.parse(data.join("\n")) } as AskEvent;
}

/**
 * Split buffered text into complete SSE blocks and the unfinished rest.
 * TECH: a block ends at a blank line ("\n\n", or "\r\n\r\n" from some servers).
 */
export function splitSseBlocks(buffer: string): { blocks: string[]; rest: string } {
  const parts = buffer.split(/\r?\n\r?\n/);
  const rest = parts.pop() ?? "";
  return { blocks: parts.filter((p) => p.trim() !== ""), rest };
}

/**
 * Ask one question; call onEvent for each event as it arrives.
 * BUSINESS: a typed question, or a desk question id (which skips the model).
 * TECH: resolves when the stream ends. Throws ApiError for an HTTP error before the
 *   stream, and the AbortError if the visitor leaves (signal).
 */
export async function askTheTape(
  body: AskRequest,
  onEvent: (event: AskEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    await readJson(res); // TECH: throws ApiError with the server's "detail"
    return;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    // TECH: stream: true keeps a multi-byte character split across chunks intact.
    buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });
    const { blocks, rest } = splitSseBlocks(done ? `${buffer}\n\n` : buffer);
    buffer = rest;
    for (const block of blocks) {
      const event = parseSseBlock(block);
      if (event) onEvent(event);
    }
    if (done) return;
  }
}
