/**
 * grid/loanQuery.ts: turn what the grid asks for into /api/loans query parameters.
 *
 * Where it sits: AG Grid (scroll, sort, filter) -> loanDatasource.ts -> [loanQuery]
 * -> GET /api/loans?offset=&limit=&sort=&filter= -> DuckDB on the server.
 *
 * BUSINESS: "largest balances first, LTV over 125 only, show me rows 200-299".
 *   The server applies it to the whole tape, so the answer is right even when the
 *   browser holds only one block of loans.
 * TECH: AG Grid's Infinite Row Model asks for rows startRow..endRow (endRow excluded)
 *   with a sortModel and a filterModel. The API wants:
 *     offset = startRow, limit = endRow - startRow        (in loans)
 *     sort   = "col:dir,col:dir"                         (AG Grid's sort order)
 *     filter = the filter model as JSON, unchanged       (backend/app/loan_query.py
 *                                                         reads AG Grid's format)
 *     question = a desk-question id ("ltv_over_125")     (the chip that is on; the
 *                                                         server ANDs its rule with
 *                                                         the filter)
 *   Empty sort, filter or question is left out, so the server uses its defaults.
 *   The SPA never builds SQL; the server checks every column name and parameterizes
 *   every value.
 */
import type { SortModelItem } from "ag-grid-community";

/** What the grid asks for. TECH: a subset of AG Grid's IGetRowsParams. */
export interface GridRequest {
  startRow: number;
  endRow: number;
  sortModel: SortModelItem[];
  filterModel: Record<string, unknown> | null;
}

/**
 * Build the /api/loans query string for one block of rows.
 * BUSINESS: rows 100-199 sorted by current UPB descending, New York only ->
 *   offset=100&limit=100&sort=current_upb:desc&question=new_york
 * TECH: URLSearchParams escapes the JSON, so quotes and braces travel safely.
 *   question is optional; null or "" sends none.
 */
export function buildLoansQuery(req: GridRequest, question: string | null = null): URLSearchParams {
  const params = new URLSearchParams({
    offset: String(req.startRow),
    limit: String(req.endRow - req.startRow),
  });
  const sort = req.sortModel.map((s) => `${s.colId}:${s.sort}`).join(",");
  if (sort) params.set("sort", sort);
  if (req.filterModel && Object.keys(req.filterModel).length > 0) {
    params.set("filter", JSON.stringify(req.filterModel));
  }
  if (question) params.set("question", question);
  return params;
}

