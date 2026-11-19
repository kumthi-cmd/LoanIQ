/**
 * components/AppHeader.tsx: the top bar of LoanIQ.
 *
 * Where it sits: App layout -> [AppHeader]; the row count comes from the current
 * screen's grid (through the layout's state).
 *
 * BUSINESS: the name, a clear "synthetic data" warning so no visitor mistakes the
 *   loans for real borrowers, and how many loans match the current filter.
 * TECH: rowCount is null until the grid's first block arrives (shown as "…").
 *   The count is in an aria-live region so screen readers announce it when a
 *   filter changes it.
 */
import { formatNumber } from "../grid/columnFormats";

interface AppHeaderProps {
  /** Loans matching the current filter; null while loading or on screens without a grid. */
  rowCount: number | null;
}

/**
 * The header bar.
 * BUSINESS: "12,345 loans" answers "how much of the tape is this filter?".
 * TECH: one loan is "1 loan", everything else "N loans".
 */
export function AppHeader({ rowCount }: AppHeaderProps) {
  const countText =
    rowCount === null ? "… loans" : `${formatNumber(rowCount, "count")} ${rowCount === 1 ? "loan" : "loans"}`;
  return (
    <header className="app-header">
      <h1 className="app-title">LoanIQ</h1>
      <span className="badge">Synthetic data - demonstration only</span>
      <span className="row-count" aria-live="polite" data-testid="row-count">
        {countText}
      </span>
    </header>
  );
}
