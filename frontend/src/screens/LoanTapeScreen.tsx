/**
 * screens/LoanTapeScreen.tsx: the Loan Tape screen (route "/").
 *
 * Where it sits: the first step of the desk's flow:
 *   [loan tape] -> slotting -> best execution -> positions and optimizer -> pool candidates
 *
 * BUSINESS: a trader's first look at a tape: headline numbers (KPI tiles), then
 *   every loan in a grid to sort and filter. Questions it answers: how big is the
 *   tape, what coupon and credit is it, which loans are delinquent or unusual.
 * TECH: on first draw, fetches the column list and the summary in parallel, then
 *   hands the columns to LoanGrid, which pages loans on its own. useEffect (a React
 *   hook) runs this fetch after the screen appears; the AbortController cancels it
 *   if the visitor leaves first. The row count goes up to the header through the
 *   layout's outlet context (App.tsx).
 */
import { useEffect, useState } from "react";
import { useOutletContext } from "react-router";
import { fetchColumns, fetchSummary } from "../api/client";
import type { ColumnInfo, Summary } from "../api/types";
import { ExplainPanel } from "../components/ExplainPanel";
import { KpiTiles } from "../components/KpiTiles";
import { LoanGrid } from "../components/LoanGrid";
import type { LayoutContext } from "../App";

/**
 * The Loan Tape screen.
 * BUSINESS: tape summary plus the full, server-paged loan grid.
 * TECH: an error loading columns or summary shows an alert instead of a blank screen.
 */
export function LoanTapeScreen() {
  const { setRowCount } = useOutletContext<LayoutContext>();
  const [columns, setColumns] = useState<ColumnInfo[] | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // TECH: start both requests together; neither depends on the other.
    const ctrl = new AbortController();
    fetchColumns(ctrl.signal).then(setColumns).catch((e: Error) => {
      if (!ctrl.signal.aborted) setError(e.message);
    });
    fetchSummary(ctrl.signal).then(setSummary).catch((e: Error) => {
      if (!ctrl.signal.aborted) setError(e.message);
    });
    // TECH: on leaving the screen, cancel requests and clear the header count.
    return () => {
      ctrl.abort();
      setRowCount(null);
    };
  }, [setRowCount]);

  return (
    <div className="screen">
      <div className="screen-head">
        <h2>Loan Tape</h2>
        <ExplainPanel screen="loan-tape" />
      </div>
      {error && (
        <div role="alert" className="grid-error">
          Could not reach the loan API: {error}
        </div>
      )}
      <KpiTiles summary={summary} />
      {columns && <LoanGrid columns={columns} onRowCount={setRowCount} />}
    </div>
  );
}
