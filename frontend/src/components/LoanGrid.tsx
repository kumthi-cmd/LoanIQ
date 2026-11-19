/**
 * components/LoanGrid.tsx: the loan tape grid.
 *
 * Where it sits: Loan Tape screen -> [LoanGrid] -> AG Grid (Infinite Row Model)
 * -> loanDatasource.ts -> GET /api/loans, 100 loans per request.
 *
 * BUSINESS: the trader's view of every loan: scroll the whole tape, sort by any
 *   field, filter (LTV greater than 125, state equals NY), and see at once how many
 *   loans match. Delinquent loans stand out in red.
 * TECH:
 *   - AgGridReact is AG Grid's React component. rowModelType="infinite" means the
 *     grid never holds the whole tape: it asks the datasource for blocks of
 *     cacheBlockSize rows as the user scrolls, and drops old blocks beyond
 *     maxBlocksInCache. Sorting and filtering reset the blocks and ask again.
 *   - The datasource and column definitions are created with useMemo (a React
 *     hook that keeps a value between redraws), so the grid is not rebuilt on every
 *     redraw of the screen.
 *   - Rows are virtualized (only rows on screen, plus rowBuffer, are drawn), but
 *     columns are not (suppressColumnVirtualisation). A tape has a fixed ~41
 *     columns, so drawing all of them costs little, and every header and filter box
 *     is then in the page for keyboard users, screen readers and Playwright.
 *   - A failed request (say a filter the server refuses) shows an alert above the
 *     grid with the server's message; the next successful request clears it.
 *   - The desk question (chip) is part of the datasource. When it changes, useMemo
 *     builds a new datasource, AG Grid sees a new `datasource` prop, drops its blocks
 *     and asks again from row 0, keeping the trader's sort and column filters.
 *   - Hidden columns (the "Columns" picker) only change each column's `hide` flag;
 *     the rows already loaded stay, because every row already holds every field.
 */
import type { ColDef } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { useMemo, useState } from "react";
import type { ColumnInfo, LoanRow } from "../api/types";
import { gridConfig } from "../grid/gridConfig";
import { loanIqGridTheme } from "../grid/gridTheme";
import { buildColumnDefs } from "../grid/loanColumns";
import { createLoanDatasource } from "../grid/loanDatasource";

/**
 * Settings every column shares.
 * BUSINESS: a filter box under each header (a "floating filter"), so a trader types
 *   "NY" under State without opening a menu. Text boxes use "contains", number boxes
 *   "equals"; the header menu offers the other options (greater than, between).
 * TECH: defined outside the component so it is one stable object, not a new one
 *   per redraw (a new object would make AG Grid re-apply every column).
 */
const DEFAULT_COL_DEF: ColDef<LoanRow> = { minWidth: 90, width: 130, resizable: true, floatingFilter: true };

interface LoanGridProps {
  /** The tape's columns from /api/loans/columns. */
  columns: ColumnInfo[];
  /** BUSINESS: called with the number of loans matching the current filter and chip. */
  onRowCount: (count: number) => void;
  /** The desk question (chip) that is on, or null. */
  question?: string | null;
  /** Column names the trader has hidden with the Columns picker. */
  hiddenColumns?: ReadonlySet<string>;
}

// TECH: one shared empty set, so the default prop is the same object every redraw
//   and does not rebuild the column definitions.
const NO_HIDDEN: ReadonlySet<string> = new Set();

/**
 * The tape grid.
 * BUSINESS: the desk's main working view of a tape.
 * TECH: getRowId uses loan_id so AG Grid can track rows across blocks.
 */
export function LoanGrid({ columns, onRowCount, question = null, hiddenColumns = NO_HIDDEN }: LoanGridProps) {
  const [error, setError] = useState<string | null>(null);
  const columnDefs = useMemo(() => buildColumnDefs(columns, hiddenColumns), [columns, hiddenColumns]);
  const datasource = useMemo(
    () =>
      createLoanDatasource(
        {
          onTotal: (total) => {
            setError(null);
            onRowCount(total);
          },
          onError: (err) => setError(err.message),
        },
        question,
      ),
    [onRowCount, question],
  );

  return (
    <div className="grid-wrap">
      {error && (
        <div role="alert" className="grid-error">
          Could not load loans: {error}
        </div>
      )}
      <div className="grid-host" data-testid="loan-grid">
        <AgGridReact<LoanRow>
          theme={loanIqGridTheme}
          columnDefs={columnDefs}
          defaultColDef={DEFAULT_COL_DEF}
          rowModelType="infinite"
          datasource={datasource}
          cacheBlockSize={gridConfig.blockSize}
          maxBlocksInCache={gridConfig.maxBlocksInCache}
          tooltipShowDelay={gridConfig.tooltipShowDelayMs}
          getRowId={(p) => String(p.data.loan_id)}
          suppressColumnVirtualisation
          rowBuffer={gridConfig.rowBuffer}
        />
      </div>
    </div>
  );
}
