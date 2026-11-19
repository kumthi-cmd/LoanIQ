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
