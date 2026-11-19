/**
 * components/AppHeader.tsx: the top bar of LoanIQ.
 *
 * Where it sits: App layout -> [AppHeader]; the row count comes from the current
 * screen's grid (through the layout's state).
 *
 * BUSINESS: the name and what it is (a mortgage capital markets desk), a clear
 *   "synthetic data" warning so no visitor mistakes the loans for real borrowers,
 *   the "Ask the tape" box (planned for Step 4, so shown but disabled), and how many
 *   loans match the current filter.
 * TECH: rowCount is null until the grid's first block arrives (shown as "…").
 *   The count is in an aria-live region so screen readers announce it when a
 *   filter changes it. The search box is a real <input> that is disabled, so it is
 *   visible and labelled but cannot be typed into or focused by Tab.
 */
import { formatNumber } from "../grid/columnFormats";

interface AppHeaderProps {
  /** Loans matching the current filter; null while loading or on screens without a grid. */
  rowCount: number | null;
}

/** TECH: the three-bar logo mark; decorative, so hidden from screen readers. */
function LogoMark() {
  return (
    <svg width="26" height="26" viewBox="0 0 26 26" aria-hidden="true">
      <rect x="1" y="1" width="24" height="24" rx="6" fill="var(--panel-2)" stroke="var(--border)" />
      <rect x="6" y="14" width="3" height="6" rx="1" fill="var(--accent)" />
      <rect x="11.5" y="10" width="3" height="10" rx="1" fill="var(--accent)" />
      <rect x="17" y="6" width="3" height="14" rx="1" fill="var(--accent)" />
    </svg>
  );
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
      <div className="brand">
        <LogoMark />
        <h1 className="app-title">LoanIQ</h1>
      </div>
      <span className="muted">Mortgage capital markets desk</span>
      <span className="badge">Synthetic data · demonstration only</span>
      <label className="ask-box">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
          strokeWidth="2" strokeLinecap="round" aria-hidden="true">
          <circle cx="11" cy="11" r="7" />
          <path d="M20 20l-3.5-3.5" />
        </svg>
        <span className="visually-hidden">Ask the tape (planned for Step 4)</span>
        <input type="search" disabled placeholder="Ask the tape: “NY loans under $150K?”" />
        <span className="tag">Planned</span>
      </label>
      <span className="row-count" aria-live="polite" data-testid="row-count">
        {countText}
      </span>
    </header>
  );
}
