/**
 * components/SlottingDialog.tsx: the Product Slotting dialog: confirm, run with
 * commentary, done.
 *
 * Where it sits: App layout -> [SlottingDialog] <- SlottingContext (run state, actions)
 * <- POST /api/slotting/run (via slottingStream.ts). Opened by the sidebar action or
 * the Slotting panel's button.
 *
 * BUSINESS: the board's three stages:
 *   1. Confirm: what will run (the tape, the rules in force, the coupon rule), that no
 *      prices are set yet, and that a rerun replaces the last result.
 *   2. Running: the progress bar, "Step 8 of 13 · Matching LLB tiers", and one
 *      commentary line per finished step with the counts the server found.
 *   3. Done: the totals, then the dialog closes itself and the Loan Tape shows the
 *      new columns ("Go now" skips the wait).
 *   A refused run (already running) or a failed one shows why, and the tape keeps
 *   the last finished result.
 * TECH:
 *   - A modal dialog: role="dialog" with aria-modal, named by its heading. Focus
 *     moves into it when it opens and when the stage changes, Tab stays inside it,
 *     and focus goes back to what opened it when it closes.
 *   - Escape cancels the confirm or error stage; during the run it acts as "Go now",
 *     since the server has already published the result.
 *   - The commentary is an ordered list with aria-live="polite", so a screen reader
 *     reads each new line as it appears.
 *   - The tape line (loans and fields) comes from GET /api/tape when the dialog opens.
 */
import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { fetchTapeInfo } from "../api/client";
import type { TapeInfo } from "../api/types";
import { fillCaption, slottingContent } from "../content/content";
import { formatNumber } from "../grid/columnFormats";
import { progress } from "../slotting/runState";
import { useSlotting } from "../slotting/SlottingContext";
import { doneNotSlotted, doneSummary, formatRunTime, rulesLine } from "../slotting/slottingText";

const words = slottingContent.dialog;
const FOCUSABLE = "button:not([disabled]), [href], [tabindex]:not([tabindex='-1'])";

/**
 * The dialog.
 * BUSINESS: run Product Slotting and watch it work.
 */
export function SlottingDialog() {
  const { run, status, cancel, start, finish } = useSlotting();
  const ref = useRef<HTMLDivElement>(null);
  const opener = useRef<Element | null>(null);
  const [tape, setTape] = useState<TapeInfo | null>(null);
  const open = run.stage !== "closed";

  // TECH: remember what had focus, fetch the tape line, and give focus back on close.
  useEffect(() => {
    if (!open) return;
    opener.current = document.activeElement;
    const ctrl = new AbortController();
    fetchTapeInfo(ctrl.signal).then(setTape).catch(() => undefined);
    return () => {
      ctrl.abort();
      if (opener.current instanceof HTMLElement) opener.current.focus();
    };
  }, [open]);

  // TECH: move focus to the first control each time the stage changes.
  useEffect(() => {
    if (open) (ref.current?.querySelector<HTMLElement>(FOCUSABLE) ?? ref.current)?.focus();
  }, [open, run.stage]);

  if (!open) return null;

  // TECH: Escape and the Tab focus trap; the handler is on the dialog only.
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Escape") {
      e.preventDefault();
      if (run.stage === "confirm" || run.stage === "error") cancel();
      else finish();
      return;
    }
    if (e.key !== "Tab" || !ref.current) return;
    const items = [...ref.current.querySelectorAll<HTMLElement>(FOCUSABLE)];
    if (items.length === 0) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  };

  return (
    <div className="modal-backdrop">
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby="slotting-dialog-title"
        className="slotting-dialog" tabIndex={-1} onKeyDown={onKeyDown}>
        {run.stage === "confirm" && (
          <ConfirmStage tape={tape} replacesAt={status?.run ? status.run_at ?? null : null}
            rules={status?.rules ? rulesLine(status.rules) : null} onCancel={cancel} onRun={start} />
        )}
        {(run.stage === "running" || run.stage === "done") && <RunStage onGoNow={finish} />}
        {run.stage === "error" && (
          <div className="dialog-section">
            <h2 id="slotting-dialog-title">{words.errorTitle}</h2>
            <p role="alert">{run.error}</p>
            <div className="dialog-actions">
              <button type="button" className="btn" onClick={cancel}>{words.close}</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

interface ConfirmProps {
  tape: TapeInfo | null;
  /** BUSINESS: the last run's time, if a run exists (it will be replaced). */
  replacesAt: string | null;
  rules: string | null;
  onCancel: () => void;
  onRun: () => void;
}

/** BUSINESS: "Run Product Slotting?" with what will run. */
function ConfirmStage({ tape, replacesAt, rules, onCancel, onRun }: ConfirmProps) {
  const tapeValue = tape
    ? fillCaption(words.tapeValue, { loans: formatNumber(tape.loans, "count"), fields: formatNumber(tape.fields, "count") })
    : "…";
  const rows: [string, ReactNode][] = [
    [words.rows.tape, tapeValue],
    [words.rows.rules, <>{rules ?? "…"} <code className="mono">{words.rulesFile}</code></>],
    [words.rows.coupons, words.couponsValue],
    [words.rows.prices, words.pricesValue],
    [words.rows.takes, words.takesValue],
  ];
  return (
    <>
      <div className="dialog-section">
        <h2 id="slotting-dialog-title">{words.confirmTitle}</h2>
        <p>{words.confirmText}</p>
      </div>
      <dl className="dialog-facts">
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      {replacesAt && <p className="dialog-warn">{fillCaption(words.replaces, { time: formatRunTime(replacesAt) })}</p>}
      <div className="dialog-actions">
        <button type="button" className="btn" onClick={onCancel}>{words.cancel}</button>
        <button type="button" className="btn btn-primary" onClick={onRun}>{words.run}</button>
      </div>
    </>
  );
}

/**
 * BUSINESS: the progress bar, the step label and the commentary; then the totals.
 * TECH: reads the run state straight from the context.
 */
function RunStage({ onGoNow }: { onGoNow: () => void }) {
  const { run } = useSlotting();
  const { percent, current, steps } = progress(run);
  const done = run.stage === "done";
  const totals = run.result?.totals;
  const label = done
    ? fillCaption(words.allDone, { steps })
    : current ? fillCaption(words.stepLabel, { step: current.step, steps: current.steps, name: current.name }) : "";
  return (
    <>
      <div className="dialog-section">
        <h2 id="slotting-dialog-title">{done ? words.doneTitle : words.runningTitle}</h2>
        <div className="run-progress-line">
          <span className={done ? "run-percent run-percent-done" : "run-percent"}>{percent}%</span>
          <span className="muted">{label}</span>
        </div>
        <div role="progressbar" aria-label={words.progress} aria-valuemin={0} aria-valuemax={100}
          aria-valuenow={percent} className="run-bar">
          <div className={done ? "run-bar-fill run-bar-done" : "run-bar-fill"} style={{ width: `${percent}%` }} />
        </div>
      </div>
      <div className="dialog-section">
        <span className="eyebrow">{words.commentary}</span>
        <ol className="run-lines" aria-live="polite">
          {run.received.slice(0, run.shown).map((s) => (
            <li key={s.step} className="run-line">{s.line}</li>
          ))}
          {!done && current && <li className="run-line run-line-current">{current.name}…</li>}
        </ol>
      </div>
      {!done && <p className="muted small dialog-note">{words.keepOpen}</p>}
      {done && totals && (
        <>
          <div className="run-summary">
            <strong>{doneSummary(totals)}</strong>
            <span>{doneNotSlotted(totals)}</span>
          </div>
          <div className="dialog-actions">
            <span className="muted">{words.opening}</span>
            <button type="button" className="btn btn-accent" onClick={onGoNow}>{words.goNow}</button>
          </div>
        </>
      )}
    </>
  );
}
