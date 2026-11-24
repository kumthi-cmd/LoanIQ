/**
 * components/ask/LoanDrawer.tsx: every field of one loan, in a panel over the screen.
 *
 * Where it sits: a loan ID in an answer or result table -> [LoanDrawer]
 *   -> GET /api/ask/loans/{loan_id} -> the agent's own get_loan tool.
 *
 * BUSINESS: the trader clicks LN72972382 in an answer and sees the whole loan: its
 *   balance, rate, FICO, LTV, status, ARM terms and flags, labelled and formatted
 *   as on the Loan Tape, without leaving the conversation.
 * TECH:
 *   - A dialog drawn by the app (role="dialog", aria-modal) rather than the browser's
 *     <dialog> element, so it behaves the same in every browser and in jsdom tests.
 *   - Focus moves to the Close button when it opens and back to whatever opened it
 *     when it closes, so keyboard users never lose their place. Escape closes it:
 *     the key handler is on the drawer itself, never on the whole page.
 *   - Fields are listed in tape order (the /api/loans/columns list), with the
 *     tape's labels and number formats (resultFormat.formatCell).
 */
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { fetchLoanRecord } from "../../api/client";
import type { ColumnInfo, LoanRecord } from "../../api/types";
import { formatCell } from "../../ask/resultFormat";
import { askTheTapeContent as words, fillCaption } from "../../content/content";

interface LoanDrawerProps {
  loanId: string;
  /** Tape columns in tape order, for labels, order and formats. */
  columns: ColumnInfo[];
  onClose: () => void;
}

/**
 * The drawer.
 * TECH: the fetch effect re-runs when loanId changes (clicking another loan while
 *   the drawer is open); the AbortController drops the older answer.
 */
export function LoanDrawer({ loanId, columns, onClose }: LoanDrawerProps) {
  const [record, setRecord] = useState<LoanRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();

  useEffect(() => {
    const ctrl = new AbortController();
    setRecord(null);
    setError(null);
    fetchLoanRecord(loanId, ctrl.signal)
      .then(setRecord)
      .catch((e: Error) => {
        if (!ctrl.signal.aborted) setError(e.message);
      });
    return () => ctrl.abort();
  }, [loanId]);

  // TECH: focus Close on open; give focus back to the opener on close.
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    return () => opener?.focus?.();
  }, []);

  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Escape") onClose();
  };

  const byName = new Map(columns.map((c) => [c.name, c]));
  // TECH: tape order first; any field the column list does not know goes last.
  const names = record
    ? [...columns.map((c) => c.name).filter((n) => n in record.loan),
       ...Object.keys(record.loan).filter((n) => !byName.has(n))]
    : [];

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <div className="loan-drawer" role="dialog" aria-modal="true" aria-labelledby={titleId}
        onKeyDown={onKey} onClick={(e) => e.stopPropagation()}>
        <div className="drawer-head">
          <h3 id={titleId} className="mono-title">{fillCaption(words.loanDrawerTitle, { loanId })}</h3>
          <button ref={closeRef} type="button" className="btn btn-small" onClick={onClose}>Close</button>
        </div>
        <p className="muted small">{words.loanDrawerNote}</p>
        {error && <div role="alert" className="grid-error">{error}</div>}
        {!record && !error && <p className="muted small">{words.thinking}</p>}
        {record && (
          <dl className="loan-fields">
            {names.map((n) => (
              <div key={n} className="loan-field">
                <dt>{byName.get(n)?.label ?? n}</dt>
                <dd className={byName.get(n)?.kind === "number" ? "num" : undefined}>
                  {formatCell(n, record.loan[n], byName) || "—"}
                </dd>
              </div>
            ))}
          </dl>
        )}
      </div>
    </div>
  );
}
