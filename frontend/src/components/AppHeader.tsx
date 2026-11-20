/**
 * components/AppHeader.tsx: the top bar of LoanIQ.
 *
 * Where it sits: App layout -> [AppHeader]; the row count comes from the current
 * screen's grid (through the layout's state).
 *
 * BUSINESS: the LoanIQ Labs logo and what the app is (a mortgage capital markets desk), a clear
 *   "synthetic data" warning so no visitor mistakes the loans for real borrowers,
 *   the "Ask the tape" box (planned for Step 4, so shown but disabled), and how many
 *   loans match the current filter.
 * TECH: the logo is brand/logo/loaniq-labs_horizontal_dark-bg_48px.svg (the README's
 *   choice for the app's dark header: a version drawn for 48 px, with a bold "LABS"),
 *   imported through the "@brand" alias so brand/ stays the only copy. It sits inside the page's one <h1> as an <img> whose alt text is
 *   "LoanIQ Labs", so the heading and the image are both named "LoanIQ Labs" for
 *   screen readers and tests. The lettering is outlined in the SVG, so it needs no font.
 *   rowCount is null until the grid's first block arrives (shown as "…").
 *   The count is in an aria-live region so screen readers announce it when a
 *   filter changes it. The search box is a real <input> that is disabled, so it is
 *   visible and labelled but cannot be typed into or focused by Tab.
 */
// TECH: importing an image file gives its published URL as a string. Vite copies
//   the SVG into the build under assets/ with a content hash in its name, so a new
//   logo is never served from a stale browser cache.
import logoUrl from "@brand/logo/loaniq-labs_horizontal_dark-bg_48px.svg";
import { formatNumber } from "../grid/columnFormats";

interface AppHeaderProps {
  /** Loans matching the current filter; null while loading or on screens without a grid. */
  rowCount: number | null;
}

/**
 * BUSINESS: the header logo is drawn for exactly this height: "LoanIQ" reads at 30 px
 *   and "LABS" at a bold 12 px, clearly legible on the navy bar. (The v1 logo at 36 px
 *   showed "LABS" thin, widely spaced and barely visible.)
 * TECH: the logo's height in CSS pixels. The SVG's own size is 144.04 x 48, so at
 *   48 px it is shown at its natural size (about 144 px wide) and nothing is scaled.
 *   It is taller than the 36 px header controls, so the header bar grows by 12 px;
 *   align-items: center in .app-header keeps the controls centred beside it.
 */
const LOGO_HEIGHT_PX = 48;

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
        <h1 className="app-title">
          <img src={logoUrl} alt="LoanIQ Labs" height={LOGO_HEIGHT_PX} className="brand-logo" />
        </h1>
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
