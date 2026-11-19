/**
 * components/DelinquencyPanel.tsx: loans by MBA delinquency status.
 *
 * Where it sits: GET /api/loans/breakdowns (dq_status) -> Loan Tape screen -> [DelinquencyPanel].
 *
 * BUSINESS: a loan that is not Current prices lower and usually cannot be delivered
 *   into an agency pool, so the desk counts them before anything else. The headline
 *   is how many loans are Current and what share of the tape that is; below it, one
 *   red bar per late status in MBA order (30, 60, 90, 120+, then foreclosure, REO and
 *   bankruptcy), so the severe end stands out. Counted in loans, because each late
 *   loan is a separate problem to solve, whatever its balance.
 * TECH: the API sends statuses in the order of api.toml [breakdowns] dq_status_order,
 *   with 0 for a status that has no loans. "Current" is the same rule as
 *   CURRENT_STATUS in backend/app/main.py and loanColumns.ts. Bars are scaled to the
 *   largest late status (barScale.ts). Red is meaning, not decoration: it marks
 *   delinquency only (.claude/rules/frontend.md).
 */
import type { StatusCount } from "../api/types";
import { loanTapeContent } from "../content/content";
import { formatNumber, formatShare } from "../grid/columnFormats";
import { CURRENT_STATUS } from "../grid/loanColumns";
import { barWidth } from "./barScale";
import { GlossaryTerm } from "./GlossaryTerm";
import { SummaryPanel } from "./SummaryPanel";

interface DelinquencyPanelProps {
  /** Statuses from the API in MBA order; null while loading. */
  statuses: StatusCount[] | null;
}

/**
 * The MBA delinquency panel.
 * BUSINESS: "Current 1,848 · 92.4% of loans", then each late status.
 * TECH: the share is of all loans on the tape (the sum of every status).
 */
export function DelinquencyPanel({ statuses }: DelinquencyPanelProps) {
  const list = statuses ?? [];
  const total = list.reduce((sum, s) => sum + s.loans, 0);
  const current = list.find((s) => s.status === CURRENT_STATUS)?.loans ?? 0;
  const late = list.filter((s) => s.status !== CURRENT_STATUS);
  const max = Math.max(0, ...late.map((s) => s.loans));
  return (
    <SummaryPanel name="MBA delinquency" loaded={statuses !== null}
      caption={loanTapeContent.captions.delinquency} title={<GlossaryTerm term="MBA delinquency" />}>
      <div className="dq-headline">
        <span className="muted">Current</span>
        <strong>{formatNumber(current, "count")}</strong>
        <span className="muted">· {formatShare(current, total)} of loans</span>
      </div>
      <ul className="bar-list">
        {late.map((s) => (
          <li key={s.status} className="bar-row bar-row-dq">
            <span className="dq-delinquent">{s.status}</span>
            <span className="bar-track" aria-hidden="true">
              <span className="bar-fill bar-fill-danger" style={{ width: barWidth(s.loans, max) }} />
            </span>
            <span className="bar-value">{formatNumber(s.loans, "count")}</span>
          </li>
        ))}
      </ul>
    </SummaryPanel>
  );
}
