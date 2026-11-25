/**
 * slotting/SlottingContext.tsx: Product Slotting's shared state for the whole app.
 *
 * Where it sits: App layout -> [SlottingProvider] -> Sidebar (the action), SlottingDialog,
 * Loan Tape (panel, notice, new columns, hover cards).
 *
 * BUSINESS: one Product Slotting for every part of the screen: the sidebar shows "Last
 *   run 11:42 AM", the dialog runs it, and the Loan Tape gains its columns and panel
 *   when the run finishes, wherever the visitor started it from.
 * TECH:
 *   - React context: a value the provider puts in the tree that any component below
 *     can read with useContext, without passing it through every component between.
 *   - status comes from GET /api/slotting/status when the app opens, so a visitor who
 *     arrives after someone else's run sees the tape already slotted.
 *   - The run: start() opens the stream (slottingStream.ts) and feeds each event to
 *     the reducer (runState.ts). While running, a timer reveals one line every
 *     stepMs (slottingConfig.ts); with prefers-reduced-motion every line shows at once.
 *     When done, the summary stays doneHoldMs, then finish() closes the dialog, takes
 *     the visitor to the Loan Tape and shows the notice.
 *   - finish() is also "Go now", and closing the dialog mid-run: the server has
 *     already published, so nothing is lost by skipping the pacing.
 *   - A failed status fetch leaves status null: the sidebar says nothing about a last
 *     run, and the dialog still works.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useRef, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router";
import { ApiError, fetchSlottingStatus } from "../api/client";
import type { SlottingStatus } from "../api/types";
import { slottingConfig } from "./slottingConfig";
import { runSlotting } from "./slottingStream";
import { INITIAL_RUN, runReducer, type RunState } from "./runState";

export interface SlottingApi {
  /** BUSINESS: the last run and the rules in force; null until known. */
  status: SlottingStatus | null;
  /** The run dialog's state. */
  run: RunState;
  /** BUSINESS: the "Loan Tape updated" notice's run, until the visitor closes it. */
  notice: SlottingStatus | null;
  open: () => void;
  cancel: () => void;
  start: () => void;
  finish: () => void;
  closeNotice: () => void;
}

const SlottingContext = createContext<SlottingApi | null>(null);

/**
 * BUSINESS: does the visitor's system ask for less motion?
 * TECH: matchMedia may be missing (old browsers, some test set-ups): then no.
 */
function prefersReducedMotion(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * The provider.
 * BUSINESS: holds the one Product Slotting the whole app shares.
 * TECH: useReducer for the dialog (runState.ts); useState for status and notice. The
 *   AbortController cancels the stream if the app unmounts mid-run.
 */
export function SlottingProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<SlottingStatus | null>(null);
  const [notice, setNotice] = useState<SlottingStatus | null>(null);
  const [run, dispatch] = useReducer(runReducer, INITIAL_RUN);
  const navigate = useNavigate();
  const location = useLocation();
  const streamCtrl = useRef<AbortController | null>(null);

  // TECH: the last run, once, when the app opens.
  useEffect(() => {
    const ctrl = new AbortController();
    fetchSlottingStatus(ctrl.signal).then(setStatus).catch(() => undefined);
    return () => ctrl.abort();
  }, []);

  // TECH: on leaving the app mid-run, stop reading the stream.
  useEffect(() => () => streamCtrl.current?.abort(), []);

  const open = useCallback(() => {
    // BUSINESS: refresh status, so "This replaces the slotting from ..." is current.
    fetchSlottingStatus().then(setStatus).catch(() => undefined);
    dispatch({ type: "open" });
  }, []);
  const cancel = useCallback(() => dispatch({ type: "cancel" }), []);

  const start = useCallback(() => {
    dispatch({ type: "start" });
    const ctrl = new AbortController();
    streamCtrl.current = ctrl;
    runSlotting((event) => {
      if (event.type === "step") dispatch({ type: "step", step: event.data });
      else if (event.type === "done") dispatch({ type: "done", result: event.data });
      else dispatch({ type: "failed", message: event.data.message });
    }, ctrl.signal).catch((err: unknown) => {
      if (ctrl.signal.aborted) return;
      dispatch({ type: "failed", message: err instanceof ApiError || err instanceof Error ? err.message : String(err) });
    });
  }, []);

  // BUSINESS: the run's result is the new status, shown everywhere at once.
  // TECH: the done event is sent while the server still holds its run lock, so it says
  //   running: true; by the time the visitor sees the totals the run is over. The
  //   screen marks it finished, then asks the server for the status to be sure.
  const finish = useCallback(() => {
    if (run.result) {
      const finished = { ...run.result, running: false };
      setStatus(finished);
      setNotice(finished);
      fetchSlottingStatus().then(setStatus).catch(() => undefined);
      if (location.pathname !== "/") navigate("/");
    }
    dispatch({ type: "close" });
  }, [run.result, location.pathname, navigate]);

  // TECH: the pacing timer: one more line every stepMs while running. It starts once
  //   per run and keeps its rhythm as steps arrive (a tick with nothing new to show
  //   does nothing). With reduced motion there is no timer: each new event shows at
  //   once, so that effect re-runs on every arrival instead.
  const [reduced] = useState(prefersReducedMotion);
  useEffect(() => {
    if (run.stage !== "running" || reduced) return;
    const timer = window.setInterval(() => dispatch({ type: "tick" }), slottingConfig.stepMs);
    return () => window.clearInterval(timer);
  }, [run.stage, reduced]);
  useEffect(() => {
    if (run.stage === "running" && reduced) dispatch({ type: "showAll" });
  }, [run.stage, reduced, run.received.length, run.result]);

  // TECH: the done summary stays doneHoldMs, then the dialog closes by itself.
  useEffect(() => {
    if (run.stage !== "done") return;
    const timer = window.setTimeout(finish, slottingConfig.doneHoldMs);
    return () => window.clearTimeout(timer);
  }, [run.stage, finish]);

  const closeNotice = useCallback(() => setNotice(null), []);
  const value = useMemo<SlottingApi>(
    () => ({ status, run, notice, open, cancel, start, finish, closeNotice }),
    [status, run, notice, open, cancel, start, finish, closeNotice],
  );
  return <SlottingContext.Provider value={value}>{children}</SlottingContext.Provider>;
}

/**
 * Read Product Slotting from any component under the provider.
 * TECH: throws if used outside it, so a missing provider fails loudly in tests.
 */
export function useSlotting(): SlottingApi {
  const api = useContext(SlottingContext);
  if (!api) throw new Error("useSlotting must be used inside SlottingProvider");
  return api;
}
