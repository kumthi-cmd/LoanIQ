/**
 * grid/loanDatasource.ts: the AG Grid Infinite Row Model datasource for the tape.
 *
 * Where it sits: AG Grid scrolls, sorts or filters -> [loanDatasource] -> loanQuery.ts
 * -> api/client.ts -> GET /api/loans.
 *
 * BUSINESS: a 50,000-loan tape scrolls like a 100-loan one. The browser only holds
 *   the blocks the trader has scrolled through, and every sort or filter is answered
 *   by the server over the whole tape.
 * TECH: an AG Grid "datasource" is an object with getRows(params). The Infinite Row
 *   Model calls it whenever it needs a block of rows (startRow..endRow), and again
 *   from the top whenever sorting or filtering changes. We answer with
 *   successCallback(rows, total). total tells the grid where the tape ends, so the
 *   scrollbar is the right size from the first block. On an error we call
 *   failCallback() (the block stays unloaded) and report it to the screen.
 */
import type { IDatasource, IGetRowsParams } from "ag-grid-community";
import { fetchLoans } from "../api/client";
import { buildLoansQuery } from "./loanQuery";

/** TECH: callbacks from the datasource to the screen. */
export interface DatasourceEvents {
  /** BUSINESS: loans matching the current filter (the header's row count). */
  onTotal: (total: number) => void;
  /** TECH: a request failed, for example a 400 for a filter the API refuses. */
  onError: (error: Error) => void;
}

/**
 * Create the datasource the Loan Tape grid reads from.
 * BUSINESS: every scroll, sort and filter goes to the server.
 * TECH: every block reports the total, which is the same for all blocks of one
 *   sort and filter, so the header count updates as soon as the first block arrives.
 */
export function createLoanDatasource(events: DatasourceEvents): IDatasource {
  return {
    getRows(params: IGetRowsParams) {
      fetchLoans(buildLoansQuery(params))
        .then((page) => {
          params.successCallback(page.rows, page.total);
          events.onTotal(page.total);
        })
        .catch((err: unknown) => {
          params.failCallback();
          events.onError(err instanceof Error ? err : new Error(String(err)));
        });
    },
  };
}
