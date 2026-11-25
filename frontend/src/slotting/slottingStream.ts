/**
 * slotting/slottingStream.ts: start a Product Slotting run and read its events as they stream.
 *
 * Where it sits: SlottingContext -> [slottingStream] -> POST /api/slotting/run
 * (Server-Sent Events, backend/app/slotting_api.py) -> each event -> the run dialog.
 *
 * BUSINESS: the visitor watches the run step by step: each check with what it found
 *   ("312 Jumbo and Non-QM loans have no agency pool"), then the totals.
 * TECH:
 *   - Same wire format as Ask the Tape's stream, so the block splitter and parser are
 *     reused from ask/askStream.ts. fetch() rather than EventSource, because the run
 *     is a POST.
 *   - A run already going is an HTTP 409 before any stream starts, which becomes an
 *     ApiError with the server's message.
 *   - The event shapes are written here by hand: OpenAPI describes JSON responses, not
 *     the events inside a stream. They mirror backend/app/slotting.py (SlottingRun) and
 *     slotting_api.py (done = the status; error = a message); the e2e test runs them
 *     end to end.
 */
import { readJson } from "../api/client";
import type { SlottingStatus } from "../api/types";
import { parseSseBlock, splitSseBlocks } from "../ask/askStream";

/**
 * One finished step.
 * BUSINESS: name says what was checked ("Checking products"); line what it found.
 * TECH: step counts from 1 to steps; percent is the server's, 0 to 100.
 */
export interface StepEvent {
  step: number;
  steps: number;
  kind: string;
  name: string;
  percent: number;
  line: string;
}

/** BUSINESS: the run's events: each step, then the totals (or why it stopped). */
export type SlottingEvent =
  | { type: "step"; data: StepEvent }
  | { type: "done"; data: SlottingStatus }
  | { type: "error"; data: { message: string } };

/**
 * Run Product Slotting; call onEvent for each event as it arrives.
 * TECH: resolves when the stream ends. Throws ApiError for an HTTP error before the
 *   stream (409: a run is already going), and the AbortError if the caller aborts.
 */
export async function runSlotting(onEvent: (event: SlottingEvent) => void, signal?: AbortSignal): Promise<void> {
  const res = await fetch("/api/slotting/run", {
    method: "POST",
    headers: { Accept: "text/event-stream" },
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
    // TECH: stream: true keeps a multi-byte character (the "·") split across chunks intact.
    buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });
    const { blocks, rest } = splitSseBlocks(done ? `${buffer}\n\n` : buffer);
    buffer = rest;
    for (const block of blocks) {
      const event = parseSseBlock(block) as SlottingEvent | null;
      if (event) onEvent(event);
    }
    if (done) return;
  }
}
