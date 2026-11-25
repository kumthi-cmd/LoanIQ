/**
 * slotting/runState.ts: the run dialog's state, as a reducer: what stage it is in and
 * how many commentary lines it has shown so far.
 *
 * Where it sits: slottingStream (events) and the pacing timer -> [runState]
 * -> SlottingContext -> SlottingDialog.
 *
 * BUSINESS: the dialog's stages, as on the "5 · Product Slotting" board:
 *   closed -> confirm (Run Product Slotting?) -> running (commentary, line by line)
 *   -> done (Loan Tape updated) -> closed. A refused or failed run shows "error".
 * TECH:
 *   - A reducer is a pure function (state, action) -> new state. React's useReducer
 *     hook keeps the state and redraws the dialog after each action, and the
 *     function can be tested on its own, with no screen.
 *   - The server sends every step at once, so "received" fills up almost instantly;
 *     "shown" counts how many of them the dialog has revealed. Each pacing tick
 *     reveals one more. The run is "done" only when every received step is shown
 *     AND the done event (the totals) has arrived, whichever comes last.
 */
import type { SlottingStatus } from "../api/types";
import type { StepEvent } from "./slottingStream";

export type Stage = "closed" | "confirm" | "running" | "done" | "error";

export interface RunState {
  stage: Stage;
  /** Steps received from the server, in order. */
  received: StepEvent[];
  /** How many of them the dialog shows as finished. */
  shown: number;
  /** BUSINESS: the done event: the run time and the totals. */
  result: SlottingStatus | null;
  /** BUSINESS: why the run did not finish (a run already going, a failure). */
  error: string | null;
}

export type RunAction =
  | { type: "open" }
  | { type: "cancel" }
  | { type: "start" }
  | { type: "step"; step: StepEvent }
  | { type: "done"; result: SlottingStatus }
  | { type: "failed"; message: string }
  | { type: "tick" }
  | { type: "showAll" }
  | { type: "close" };

export const INITIAL_RUN: RunState = { stage: "closed", received: [], shown: 0, result: null, error: null };

/**
 * TECH: running becomes done once every received step is shown and the totals are in.
 */
function settle(state: RunState): RunState {
  if (state.stage === "running" && state.result && state.shown >= state.received.length) {
    return { ...state, stage: "done" };
  }
  return state;
}

/**
 * The reducer.
 * BUSINESS: open shows the confirm question; start begins a fresh run; cancel and
 *   close put the dialog away. Steps and the totals arrive from the stream; ticks
 *   reveal one line each. A failure stops the run with its message.
 * TECH: actions that do not fit the stage (a late tick after close) change nothing.
 */
export function runReducer(state: RunState, action: RunAction): RunState {
  switch (action.type) {
    case "open":
      return state.stage === "closed" || state.stage === "error" ? { ...INITIAL_RUN, stage: "confirm" } : state;
    case "cancel":
      return state.stage === "confirm" || state.stage === "error" ? INITIAL_RUN : state;
    case "start":
      return state.stage === "confirm" ? { ...INITIAL_RUN, stage: "running" } : state;
    case "step":
      return state.stage === "running" ? { ...state, received: [...state.received, action.step] } : state;
    case "done":
      return state.stage === "running" ? settle({ ...state, result: action.result }) : state;
    case "failed":
      return state.stage === "running" || state.stage === "confirm"
        ? { ...state, stage: "error", error: action.message } : state;
    case "tick":
      return state.stage === "running"
        ? settle({ ...state, shown: Math.min(state.shown + 1, state.received.length) }) : state;
    case "showAll":
      return state.stage === "running" ? settle({ ...state, shown: state.received.length }) : state;
    case "close":
      return INITIAL_RUN;
    default:
      return state;
  }
}

/**
 * What the progress line shows.
 * BUSINESS: "62%" and "Step 8 of 13 · Matching LLB tiers": the percent of the last
 *   line shown, and the step being worked on next (or "all done").
 * TECH: steps is the run's step count once any step has arrived (0 before).
 */
export function progress(state: RunState): { percent: number; current: StepEvent | null; steps: number } {
  const last = state.shown > 0 ? state.received[state.shown - 1] : null;
  const current = state.received[state.shown] ?? null;
  const steps = state.received[0]?.steps ?? 0;
  return { percent: state.stage === "done" ? 100 : last?.percent ?? 0, current, steps };
}
