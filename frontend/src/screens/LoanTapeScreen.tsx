/**
 * screens/LoanTapeScreen.tsx: the Loan Tape screen (route "/").
 *
 * Where it sits: the first step of the desk's flow:
 *   [loan tape] -> slotting -> best execution -> positions and optimizer -> pool candidates
 *
 * BUSINESS: a trader's first look at a seller's tape, top to bottom:
 *   1. the title line: how wide the tape is (fields) and how many sellers are in it;
 *   2. the headline numbers (KPI tiles): loans, balance, WAC, WA FICO, WA LTV, late loans;
 *   3. three panels on its shape: program mix (who can buy it), note-rate buckets
 *      (which coupons it fits), MBA delinquency (how much is late);
 *   4. desk-question chips (LTV over 125, New York, ...) that filter the grid in one click;
 *   5. the grid of every loan, sorted and filtered on the server.
 *   The "Explain this screen" button opens a panel on the right that says what all of
 *   this means. It starts closed so the grid has room for every default column.
 *   Every number is computed by the API from the real (synthetic) tape.
 * TECH:
 *   - On first draw, five API calls start together (columns, summary, breakdowns,
 *     question counts, tape line); none depends on another. useEffect (a React hook)
 *     runs them after the screen appears; the AbortController cancels them if the
 *     visitor leaves first. Any failure shows one alert instead of a blank screen.
 *   - The screen owns the UI state the pieces share: which chip is on, which columns
 *     are hidden, whether the explanation is open, and the grid's matching count.
 *     The count also goes up to the header through the layout's outlet context.
 *   - Layout is flex with wrapping: at narrow widths the explanation moves under the
 *     grid and the three panels stack (styles.css).
 */
import { useCallback, useEffect, useState } from "react";
import { useOutletContext } from "react-router";
import { fetchBreakdowns, fetchColumns, fetchQuestionCounts, fetchSummary, fetchTapeInfo } from "../api/client";
import type { Breakdowns, ColumnInfo, QuestionCount, Summary, TapeInfo } from "../api/types";
import { ColumnPicker } from "../components/ColumnPicker";
import { DelinquencyPanel } from "../components/DelinquencyPanel";
import { DeskQuestionChips } from "../components/DeskQuestionChips";
import { ExplainPanel } from "../components/ExplainPanel";
import { KpiTiles } from "../components/KpiTiles";
import { LoanGrid } from "../components/LoanGrid";
import { NoteRatePanel } from "../components/NoteRatePanel";
import { ProgramMixPanel } from "../components/ProgramMixPanel";
import { fillCaption, loanTapeContent } from "../content/content";
import { formatNumber } from "../grid/columnFormats";
import { DEFAULT_VISIBLE_COLUMNS, gridConfig } from "../grid/gridConfig";
import type { LayoutContext } from "../App";

/**
 * The hidden-column set for a freshly loaded column list.
 * BUSINESS: the grid opens on the fields a trader reads first (gridConfig.ts).
 * TECH: every column not in DEFAULT_VISIBLE_COLUMNS starts hidden.
 */
function defaultHidden(columns: ColumnInfo[]): Set<string> {
  return new Set(columns.map((c) => c.name).filter((n) => !DEFAULT_VISIBLE_COLUMNS.includes(n)));
}

/** TECH: "…" until a count is known, else the count with commas. */
const countOrDots = (n: number | null | undefined) => (n === null || n === undefined ? "…" : formatNumber(n, "count"));

/**
 * The Loan Tape screen.
 * BUSINESS: tape summary, shape, desk questions and the full, server-paged loan grid.
 * TECH: setState functions from useState are stable, so the effect runs once.
 */
export function LoanTapeScreen() {
  const { setRowCount } = useOutletContext<LayoutContext>();
  const [columns, setColumns] = useState<ColumnInfo[] | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [summary, setSummary] = useState<Summary | null>(null);
  const [breakdowns, setBreakdowns] = useState<Breakdowns | null>(null);
  const [questionCounts, setQuestionCounts] = useState<QuestionCount[] | null>(null);
  const [tape, setTape] = useState<TapeInfo | null>(null);
  const [question, setQuestion] = useState<string | null>(null);
  const [matching, setMatching] = useState<number | null>(null);
  // BUSINESS: the explanation starts closed, so the grid gets the full width and all
  //   12 default columns show at 1440 px; "Explain this screen" opens it (Step 1g).
  const [explainOpen, setExplainOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // TECH: start every request together; each fills its own piece of the screen.
    const ctrl = new AbortController();
    const fail = (e: Error) => {
      if (!ctrl.signal.aborted) setError(e.message);
    };
    fetchColumns(ctrl.signal)
      .then((cols) => {
        setHidden(defaultHidden(cols));
        setColumns(cols);
      })
      .catch(fail);
    fetchSummary(ctrl.signal).then(setSummary).catch(fail);
    fetchBreakdowns(ctrl.signal).then(setBreakdowns).catch(fail);
    fetchQuestionCounts(ctrl.signal).then(setQuestionCounts).catch(fail);
    fetchTapeInfo(ctrl.signal).then(setTape).catch(fail);
    // TECH: on leaving the screen, cancel requests and clear the header count.
    return () => {
      ctrl.abort();
      setRowCount(null);
    };
  }, [setRowCount]);

  // BUSINESS: the grid's matching count shows in the header and the grid footer.
  // TECH: useCallback keeps one function between redraws, so LoanGrid's datasource
  //   (which depends on it) is not rebuilt on every redraw.
  const onRowCount = useCallback(
    (n: number) => {
      setMatching(n);
      setRowCount(n);
    },
    [setRowCount],
  );

  const { captions } = loanTapeContent;
  return (
    <div className="screen">
      <div className="screen-title-row">
        <div className="screen-title">
          <span className="eyebrow">{loanTapeContent.eyebrow}</span>
          <h2>Loan Tape</h2>
        </div>
        <span className="muted tape-line">
          {fillCaption(loanTapeContent.tapeLine, { fields: countOrDots(tape?.fields), sellers: countOrDots(tape?.sellers) })}
        </span>
        <div className="title-actions">
          {columns && <ColumnPicker columns={columns} hidden={hidden} onChange={setHidden} />}
          <button type="button" className="btn" disabled>
            Export CSV <span className="tag">Planned</span>
          </button>
          <button type="button" className="btn btn-accent" aria-expanded={explainOpen}
            onClick={() => setExplainOpen((o) => !o)}>
            {explainOpen ? "Hide explanation" : "Explain this screen"}
          </button>
        </div>
      </div>

      {error && (
        <div role="alert" className="grid-error">
          Could not reach the loan API: {error}
        </div>
      )}

      <div className="screen-body">
        <div className="screen-main">
          <KpiTiles summary={summary} />
          <div className="panels">
            <ProgramMixPanel programs={breakdowns?.programs ?? null} />
            <NoteRatePanel buckets={breakdowns?.note_rates ?? null} />
            <DelinquencyPanel statuses={breakdowns?.dq_status ?? null} />
          </div>
          <DeskQuestionChips counts={questionCounts} active={question} onChange={setQuestion} />
          <p className="panel-note">{captions.panelsScope}</p>
          <section className="grid-card" aria-label="Loan grid">
            {columns && (
              <LoanGrid columns={columns} onRowCount={onRowCount} question={question} hiddenColumns={hidden} />
            )}
            <div className="grid-foot">
              <span data-testid="grid-showing">
                {fillCaption(captions.gridShowing, { matching: countOrDots(matching), total: countOrDots(tape?.loans) })}
                {" · "}
                {fillCaption(captions.gridPaging, { blockSize: gridConfig.blockSize })}
              </span>
              <span>{captions.gridServer}</span>
            </div>
          </section>
        </div>
        {explainOpen && <ExplainPanel screen="loan-tape" onClose={() => setExplainOpen(false)} />}
      </div>
    </div>
  );
}
