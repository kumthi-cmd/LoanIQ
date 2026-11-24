/**
 * Tests for ask/askStream.ts: reading POST /api/ask's Server-Sent Events.
 *
 * BUSINESS: protects "the visitor watches the agent work": every tool call and the
 *   answer must reach the screen even when the network splits an event (or a
 *   character such as "€" or "…") across two chunks, and a refused question must
 *   show the server's reason instead of an empty answer.
 * TECH: fetch is mocked with a real Response whose body is a ReadableStream fed in
 *   hand-chosen chunks.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import { askTheTape, parseSseBlock, splitSseBlocks, type AskEvent } from "./askStream";

afterEach(() => vi.unstubAllGlobals());

/** A streamed Response from text chunks, as bytes. */
function streamOf(chunks: (string | Uint8Array)[]): Response {
  const enc = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(ctrl) {
      for (const c of chunks) ctrl.enqueue(typeof c === "string" ? enc.encode(c) : c);
      ctrl.close();
    },
  });
  return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

describe("parseSseBlock", () => {
  it("reads the event name and its JSON data", () => {
    expect(parseSseBlock('event: answer\ndata: {"text":"20 loans"}')).toEqual({ type: "answer", data: { text: "20 loans" } });
  });

  it("joins multi-line data and ignores comments", () => {
    expect(parseSseBlock(': keep-alive\nevent: done\ndata: {"a":\ndata: 1}')).toEqual({ type: "done", data: { a: 1 } });
  });

  it("returns null for a block with no event name or no data", () => {
    expect(parseSseBlock(": ping")).toBeNull();
    expect(parseSseBlock('data: {"x":1}')).toBeNull();
    expect(parseSseBlock("event: answer")).toBeNull();
  });
});

describe("splitSseBlocks", () => {
  it("keeps the unfinished event for the next chunk, with LF or CRLF line ends", () => {
    const { blocks, rest } = splitSseBlocks('event: a\ndata: 1\n\nevent: b\r\ndata: 2\r\n\r\nevent: c\ndata');
    expect(blocks).toEqual(["event: a\ndata: 1", "event: b\r\ndata: 2"]);
    expect(rest).toBe("event: c\ndata");
  });
});

describe("askTheTape", () => {
  it("delivers every event in order, even when chunks split events and characters", async () => {
    const answer = 'event: answer\ndata: {"text":"WAC 6.4% … done","provider":"anthropic","model":"m","notice":null}\n\n';
    const bytes = new TextEncoder().encode(answer);
    const cut = answer.indexOf("…") + 1; // TECH: inside the 3-byte "…"
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(streamOf([
      'event: tool_call\ndata: {"id":"c1","name":"query_tape","input":{}}\n',
      "\nevent: tool_res",
      'ult\ndata: {"id":"c1","name":"query_tape","status":"ok"}\n\n',
      bytes.slice(0, cut), bytes.slice(cut),
      'event: done\ndata: {"cost_usd":"0.001000"}', // TECH: no final blank line
    ]))));
    const events: AskEvent[] = [];
    await askTheTape({ question: "WAC?" }, (e) => events.push(e));
    expect(events.map((e) => e.type)).toEqual(["tool_call", "tool_result", "answer", "done"]);
    expect((events[2].data as { text: string }).text).toBe("WAC 6.4% … done");
  });

  it("posts the question as JSON", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(streamOf([])));
    vi.stubGlobal("fetch", fetchMock);
    await askTheTape({ question: "How many loans?" }, () => {});
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/ask");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ question: "How many loans?" });
  });

  it("throws the server's reason for a refused question", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(
      new Response(JSON.stringify({ detail: "Questions are limited to 500 characters." }), { status: 400 }))));
    const err = await askTheTape({ question: "x" }, () => {}).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).message).toBe("Questions are limited to 500 characters.");
  });
});
