/**
 * Tests for slotting/runState.ts: the run dialog's stages and its line-by-line pacing.
 *
 * BUSINESS: protects "the visitor reads one line at a time and sees the totals only
 *   when every line is shown": the server sends all 13 steps at once, so the dialog
 *   must not jump to done early, and must not stall if the totals arrive last. A
 *   refused or failed run shows why; a stray timer after closing changes nothing.
 * TECH: the reducer is a pure function, so each case is a list of actions.
 */
import { describe, expect, it } from "vitest";
import { RUN, STEPS } from "./slottingFixtures";
import { INITIAL_RUN, progress, runReducer, type RunAction, type RunState } from "./runState";

const play = (actions: RunAction[], from: RunState = INITIAL_RUN) => actions.reduce(runReducer, from);
const received: RunAction[] = STEPS.map((step) => ({ type: "step", step }));

describe("runReducer", () => {
  it("opens on the confirm question and cancels back to closed", () => {
    expect(play([{ type: "open" }]).stage).toBe("confirm");
    expect(play([{ type: "open" }, { type: "cancel" }])).toEqual(INITIAL_RUN);
  });

  it("shows one line per tick, and is done only when every line is shown and the totals are in", () => {
    let s = play([{ type: "open" }, { type: "start" }, ...received, { type: "done", result: RUN }]);
    expect(s.stage).toBe("running");
    expect(s.shown).toBe(0);
    s = play([{ type: "tick" }, { type: "tick" }], s);
    expect([s.stage, s.shown]).toEqual(["running", 2]);
    s = runReducer(s, { type: "tick" });
    expect([s.stage, s.shown]).toEqual(["done", 3]);
  });

  it("waits for the totals if the lines run out first", () => {
    let s = play([{ type: "open" }, { type: "start" }, ...received, { type: "showAll" }]);
    expect([s.stage, s.shown]).toEqual(["running", 3]);
    s = runReducer(s, { type: "done", result: RUN });
    expect(s.stage).toBe("done");
    expect(s.result).toBe(RUN);
  });

  it("never shows more lines than have arrived", () => {
    const s = play([{ type: "open" }, { type: "start" }, received[0], { type: "tick" }, { type: "tick" }]);
    expect(s.shown).toBe(1);
  });

  it("shows why a run failed, and can be closed or reopened", () => {
    const s = play([{ type: "open" }, { type: "start" }, { type: "failed", message: "already running" }]);
    expect([s.stage, s.error]).toEqual(["error", "already running"]);
    expect(runReducer(s, { type: "cancel" })).toEqual(INITIAL_RUN);
    expect(runReducer(s, { type: "open" }).stage).toBe("confirm");
  });

  it("ignores actions that do not fit the stage", () => {
    expect(play([{ type: "tick" }, received[0], { type: "start" }])).toEqual(INITIAL_RUN);
    const running = play([{ type: "open" }, { type: "start" }]);
    expect(runReducer(running, { type: "open" })).toBe(running);
    expect(runReducer(running, { type: "cancel" })).toBe(running);
  });
});

describe("progress", () => {
  it("gives the last shown line's percent and the step being worked on", () => {
    const s = play([{ type: "open" }, { type: "start" }, ...received, { type: "tick" }]);
    const p = progress(s);
    expect(p.percent).toBe(STEPS[0].percent);
    expect(p.current?.name).toBe("Checking agency eligibility");
    expect(p.steps).toBe(3);
  });

  it("says 100% when done and 0% before any line", () => {
    expect(progress(play([{ type: "open" }, { type: "start" }])).percent).toBe(0);
    const done = play([{ type: "open" }, { type: "start" }, ...received, { type: "showAll" }, { type: "done", result: RUN }]);
    expect(progress(done)).toMatchObject({ percent: 100, current: null });
  });
});
