/**
 * grid/gridConfig.ts: the loan grid's paging, tooltip and default-column settings.
 *
 * BUSINESS: how many loans the grid fetches per request, how many it keeps in
 *   memory, and which of the tape's ~41 fields a trader sees first. ILLUSTRATIVE
 *   engineering and display choices, not industry rules.
 * TECH: blockSize (loans per request) must not exceed the API's max_limit (500, in
 *   backend/app/config/api.toml), or the server caps the block and the grid would
 *   show gaps. 100 matches the API's default_limit. maxBlocksInCache x blockSize is
 *   the most loans the browser holds at once (here 2,000). rowBuffer is how many
 *   rows above and below the visible ones are drawn, so a short scroll shows no
 *   blank rows. Times in milliseconds.
 */
export const gridConfig = {
  blockSize: 100,
  maxBlocksInCache: 20,
  rowBuffer: 10,
  tooltipShowDelayMs: 400,
} as const;

/**
 * The columns shown when the screen opens, in the order they appear on the tape.
 * BUSINESS: the fields a trader reads first on any tape: who sold it, what it is
 *   (program, product), where (state), its coupon and size (note rate, current UPB),
 *   its credit (FICO, LTV, DTI), whether it pays (DQ status) and who lives there
 *   (occupancy). Every other field stays one click away under "Columns".
 * TECH: names are tape columns from /api/loans/columns; a name the tape does not
 *   have is ignored. loan_id is always shown and pinned (loanColumns.ts).
 */
export const DEFAULT_VISIBLE_COLUMNS: readonly string[] = [
  "loan_id", "seller", "program", "product", "state", "note_rate",
  "current_upb", "fico", "ltv", "dti", "dq_status", "occupancy",
];

/**
 * Starting width of each default column, in CSS pixels, fitted to its content.
 * BUSINESS: at 1440 px, the width the "1 · Loan Tape" design board is drawn for, all
 *   12 default columns show without scrolling sideways while the explanation is
 *   closed (its default), and Loan ID through FICO still show with it open. Before
 *   Step 1g every column was 130 px and only about 6 fitted. ILLUSTRATIVE display
 *   choices, sized like the board's table: narrow for 3-digit FICO and 2-letter
 *   state, wide for seller names. A trader can still drag any column wider.
 * TECH: applied in buildColumnDefs (loanColumns.ts); a column not listed keeps the
 *   grid default (LoanGrid.tsx). The sum must stay within the grid's width at 1440 px
 *   with the explanation closed (about 1,150 px); Playwright checks it in a real
 *   browser (e2e/tests/loan-tape-layout.spec.ts).
 */
export const DEFAULT_COLUMN_WIDTHS: Readonly<Record<string, number>> = {
  loan_id: 92, seller: 173, program: 100, product: 94, state: 60, note_rate: 106,
  current_upb: 120, fico: 60, ltv: 72, dti: 72, dq_status: 86, occupancy: 100,
};
