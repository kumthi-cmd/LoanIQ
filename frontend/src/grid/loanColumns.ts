/**
 * grid/loanColumns.ts: build AG Grid column definitions from /api/loans/columns.
 *
 * Where it sits: GET /api/loans/columns -> [loanColumns] -> LoanGrid -> AG Grid.
 *
 * BUSINESS: the grid shows every tape field in tape order, with readable headers,
 *   loan_id pinned so a trader never loses track of which loan a row is, numbers
 *   lined up on the decimal point, and delinquent loans shown in red.
 * TECH: an AG Grid ColDef describes one column: field (which key of the row),
 *   headerName, how to format a value (valueFormatter), filter, alignment, pinning.
 *   The columns come from the API, so a new tape field appears in the grid without
 *   a front-end change. The column "kind" from the API decides the filter:
 *     text    -> agTextColumnFilter, contains / equals
 *     number  -> agNumberColumnFilter, equals / greater than / less than / between
 *     date, boolean -> sortable but not filterable yet (the API has no date or
 *                      boolean filter, so offering one would only produce errors)
 *   The filter options match exactly what backend/app/loan_query.py accepts.
 */
import type { CellClassParams, ColDef, ValueFormatterParams } from "ag-grid-community";
import type { ColumnInfo, LoanRow } from "../api/types";
import { columnTerms, termTooltip } from "../content/content";
import { formatBoolean, formatDate, formatNumber, numberFormatFor } from "./columnFormats";

// BUSINESS: the loan key, pinned on the left.
export const PINNED_COLUMN = "loan_id";
// BUSINESS: the delinquency status column. Every status other than Current is
//   delinquent (30, 60, 90, 120+, FC, BK, REO). TECH: the same rule as
//   CURRENT_STATUS in backend/app/main.py, which the Delinquent loans tile counts.
export const DQ_COLUMN = "dq_status";
export const CURRENT_STATUS = "Current";

// TECH: the AG Grid filter options the API supports, per column kind.
export const TEXT_FILTER_OPTIONS = ["contains", "equals"];
export const NUMBER_FILTER_OPTIONS = ["equals", "greaterThan", "lessThan", "inRange"];

type Formatter = (p: ValueFormatterParams<LoanRow>) => string;

/**
 * Is this dq_status delinquent?
 * BUSINESS: anything but Current needs the desk's attention: it prices lower and
 *   cannot go into most agency pools. TECH: blank (null) is not flagged.
 */
export function isDelinquent(status: unknown): boolean {
  return typeof status === "string" && status !== "" && status !== CURRENT_STATUS;
}

/**
 * The kind-specific part of a column: formatting, alignment and filter.
 * BUSINESS: numbers right-aligned so digits line up; filters a desk can use.
 * TECH: "rightAligned" is a built-in AG Grid column type that right-aligns both the
 *   cell and the header.
 */
function kindSettings(col: ColumnInfo): Partial<ColDef<LoanRow>> {
  switch (col.kind) {
    case "number": {
      const format = numberFormatFor(col.name);
      const formatter: Formatter = (p) => formatNumber(p.value, format);
      return {
        type: "rightAligned",
        valueFormatter: formatter,
        filter: "agNumberColumnFilter",
        filterParams: { filterOptions: NUMBER_FILTER_OPTIONS, maxNumConditions: 2 },
      };
    }
    case "date": {
      const formatter: Formatter = (p) => formatDate(p.value);
      return { valueFormatter: formatter, filter: false };
    }
    case "boolean": {
      const formatter: Formatter = (p) => formatBoolean(p.value);
      return { valueFormatter: formatter, filter: false };
    }
    default:
      return {
        filter: "agTextColumnFilter",
        filterParams: { filterOptions: TEXT_FILTER_OPTIONS, maxNumConditions: 2 },
      };
  }
}

/**
 * Turn the API's column list into AG Grid column definitions.
 * BUSINESS: one grid column per tape field, ready to sort and filter.
 * TECH: input is the /api/loans/columns array in tape order; output keeps that order.
 *   headerTooltip comes from the glossary through content/loan-columns.json "terms";
 *   columns with no term get no tooltip. dq_status gets the "dq-delinquent" class
 *   (red text, styles.css) through cellClassRules, which AG Grid re-checks per cell.
 */
export function buildColumnDefs(columns: ColumnInfo[]): ColDef<LoanRow>[] {
  return columns.map((col) => {
    const term = columnTerms[col.name];
    const def: ColDef<LoanRow> = {
      field: col.name,
      colId: col.name,
      headerName: col.label,
      headerTooltip: term ? termTooltip(term) : undefined,
      sortable: true,
      ...kindSettings(col),
    };
    if (col.name === PINNED_COLUMN) {
      def.pinned = "left";
      def.lockPinned = true;
    }
    if (col.name === DQ_COLUMN) {
      def.cellClassRules = {
        "dq-delinquent": (p: CellClassParams<LoanRow>) => isDelinquent(p.value),
      };
    }
    return def;
  });
}
