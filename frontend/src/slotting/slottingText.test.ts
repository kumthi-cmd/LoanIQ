/**
 * Tests for slotting/slottingText.ts and slotting/slottingStream.ts.
 *
 * BUSINESS: the sentences the visitor reads are built from the API's numbers and
 *   content's words: the rules line ("12 rules in 4 spec stories: LLB tiers $85K to
 *   $275K, NY, PR, Low FICO"), the done summary and the not-slotted reasons in the
 *   order the checks run. The run's stream must deliver every step and the totals,
 *   even when the network splits an event, and a refused run (HTTP 409) must say why.
 * TECH: fetch is mocked with a real Response over a ReadableStream.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import { RULES, RUN, STEPS, streamText } from "./slottingFixtures";
import { runSlotting, type SlottingEvent } from "./slottingStream";
import { doneNotSlotted, doneSummary, formatRunTime, reasonsLine, rulesLine } from "./slottingText";

afterEach(() => vi.unstubAllGlobals());

describe("slottingText", () => {
  it("summarises the rules in force", () => {
    expect(rulesLine(RULES)).toBe("12 rules in 4 spec stories: LLB tiers $85K to $275K, NY, PR, Low FICO");
  });

  it("lists the not-slotted reasons in check order with their counts", () => {
    expect(reasonsLine(RUN.totals!)).toBe("312 No agency pool, 85 No TBA product, 136 Delinquent");
    expect(doneNotSlotted(RUN.totals!)).toMatch(/^533 not slotted: 312 No agency pool/);
  });

  it("writes the done summary from the totals", () => {
    expect(doneSummary(RUN.totals!)).toBe("1,467 of 2,000 loans slotted: 1,104 with a spec story, 363 generic TBA.");
  });

  it("shows a run time as hours and minutes, and nothing for no run", () => {
    expect(formatRunTime(RUN.run_at)).toMatch(/^\d{1,2}:\d{2} (AM|PM)$/);
    expect(formatRunTime(null)).toBe("");
  });
});

describe("runSlotting", () => {
  it("delivers every step, then the totals, even when chunks split an event", async () => {
    const text = streamText();
    const cut = text.indexOf("Checking");
    const enc = new TextEncoder();
    const body = new ReadableStream<Uint8Array>({
      start(ctrl) {
        ctrl.enqueue(enc.encode(text.slice(0, cut)));
        ctrl.enqueue(enc.encode(text.slice(cut)));
        ctrl.close();
      },
    });
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(body, { status: 200 }))));
    const events: SlottingEvent[] = [];
    await runSlotting((e) => events.push(e));
    expect(events.map((e) => e.type)).toEqual(["step", "step", "step", "done"]);
    expect(events[1].data).toEqual(STEPS[1]);
    expect(events[3].data).toEqual(RUN);
    expect(vi.mocked(fetch).mock.calls[0][1]?.method).toBe("POST");
  });

  it("throws the server's reason when a run is already going (HTTP 409)", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(
      JSON.stringify({ detail: "Product Slotting is already running" }), { status: 409 }))));
    await expect(runSlotting(() => undefined)).rejects.toEqual(new ApiError(409, "Product Slotting is already running"));
  });
});
