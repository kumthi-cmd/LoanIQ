/**
 * components/ask/QueryResultTable.tsx: the rows behind one query in an answer.
 *
 * Where it sits: AnswerTurn -> [QueryResultTable] -> GET /api/ask/queries/{id}
 *   loan ID -> LoanDrawer;  "Open in Loan Tape" -> Loan Tape screen (/?filter=...)
 *
 * BUSINESS: the loans (or groups) an answer is about, formatted like the Loan Tape.
 *   The first 8 rows show, as on the design board, with "Show all" for the rest
 *   (up to the 500-row cap). "Open in Loan Tape" opens the full grid with the same
 *   filter; when the filter cannot be shown as column filters, the button is
 *   disabled and says why. There is no "Send to Slotting": slotting is a Loan Tape
 *   action from Step 5, not a screen (docs/decisions.md, 2026-11-25).
 *   A loan-level result also carries the Loan Tape's 12 default columns, added by
 *   the server (Step 4c), so the table is drawn as stored, column for column. It is
 *   packed to its data by CSS (styles.css .result-table), not stretched.
 * TECH:
 *   - The model saw only 20 rows; the screen fetches every row by query id. A rerun
 *     already holds its rows (initial), so it does not fetch.
 *   - Results expire on the server after an hour; a 404 then shows a short message
 *     instead of an empty table.
 *   - Rows arrive as arrays in `columns` order (smaller JSON than objects).
 */
import { useEffect, useState } from "react";
import { Link } from "react-router";
import { fetchStoredQuery } from "../../api/client";
import type { ColumnInfo, LoanTapeLink, StoredQuery } from "../../api/types";
import { loanTapeUrl } from "../../ask/loanTapeUrl";
import { columnLabel, formatCell, isNumericColumn, LOAN_ID_COLUMN } from "../../ask/resultFormat";
import { askTheTapeContent as words, fillCaption } from "../../content/content";
import { formatNumber } from "../../grid/columnFormats";

/** BUSINESS: rows shown before "Show all" (the design board shows 8). */
export const PREVIEW_ROWS = 8;

interface QueryResultTableProps {
  queryId: string;
  /** TECH: the rows already in hand (a saved-query rerun); skips the fetch. */
  initial?: StoredQuery;
  /** TECH: the Loan Tape link from the tool_result event, used until the rows arrive. */
  link?: LoanTapeLink | null;
  /** Tape column name -> column info, for labels and formats. */
  columns: Map<string, ColumnInfo>;
  onOpenLoan: (loanId: string) => void;
}

/**
 * One result table.
 * TECH: the effect fetches when there are no initial rows; the AbortController
 *   cancels the request if the answer is cleared ("New thread") first.
 */
export function QueryResultTable({ queryId, initial, link, columns, onOpenLoan }: QueryResultTableProps) {
  const [result, setResult] = useState<StoredQuery | null>(initial ?? null);
  const [error, setError] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    if (initial) return;
    const ctrl = new AbortController();
    fetchStoredQuery(queryId, ctrl.signal)
      .then(setResult)
      .catch((e: Error) => {
        if (!ctrl.signal.aborted) setError(e.message);
      });
    return () => ctrl.abort();
  }, [queryId, initial]);

  const tapeLink = result?.loan_tape ?? link ?? null;
  const url = loanTapeUrl(tapeLink);

  if (error) return <div role="alert" className="grid-error">{error}</div>;
  if (!result) return <p className="muted small">{words.thinking}</p>;

  const rows = showAll ? result.rows : result.rows.slice(0, PREVIEW_ROWS);
  const loanCol = result.columns.indexOf(LOAN_ID_COLUMN);
  const numeric = result.columns.map((c, i) => isNumericColumn(c, columns, result.rows[0]?.[i]));
  const caption = result.truncated
    ? fillCaption(words.rowsCapped, { total: formatNumber(result.total_rows, "count"), returned: formatNumber(result.row_count, "count") })
    : fillCaption(words.rowsShown, { shown: formatNumber(rows.length, "count"), total: formatNumber(result.row_count, "count") });

  return (
    <div className="result">
      <div className="result-table-wrap">
        <table className="result-table">
          <caption className="visually-hidden">{result.title}</caption>
          <thead>
            <tr>
              {result.columns.map((c, i) => (
                <th key={c} scope="col" className={numeric[i] ? "num" : undefined}>{columnLabel(c, columns)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, r) => (
              <tr key={loanCol >= 0 ? String(row[loanCol]) : r}>
                {row.map((value, i) => (
                  <td key={result.columns[i]} className={numeric[i] ? "num" : undefined}>
                    {i === loanCol && typeof value === "string" ? (
                      <button type="button" className="loan-id-link" onClick={() => onOpenLoan(value)}>{value}</button>
                    ) : (
                      formatCell(result.columns[i], value, columns)
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        <div className="result-foot">
          <span>{caption}</span>
          {result.row_count > PREVIEW_ROWS && (
            <button type="button" className="btn btn-small" onClick={() => setShowAll((s) => !s)}>
              {showAll ? words.showFewer : fillCaption(words.showAll, { count: formatNumber(result.row_count, "count") })}
            </button>
          )}
        </div>
      </div>
      <div className="result-actions">
        {url ? (
          <Link className="btn" to={url}>{words.openInLoanTape}</Link>
        ) : (
          <button type="button" className="btn" disabled
            title={fillCaption(words.cannotOpen, { reason: tapeLink?.reason ?? "" })}>
            {words.openInLoanTape}
          </button>
        )}
        {!url && tapeLink?.reason && (
          <span className="muted small">{fillCaption(words.cannotOpen, { reason: tapeLink.reason })}</span>
        )}
      </div>
    </div>
  );
}
