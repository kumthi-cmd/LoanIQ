/**
 * grid/gridConfig.ts: the loan grid's paging, tooltip and default-column settings.
 *
 * BUSINESS: how many loans the grid fetches per request, how many it keeps in
 *   memory, and which of the tape's ~41 fields a trader sees first. ILLUSTRATIVE
 *   engineering and display choices, not industry rules.
 *   WHICH columns show first is not here: it lives once, in
 *   backend/app/config/api.toml [columns], and reaches the grid as each column's
 *   default_visible flag (Step 4c), because Ask the Tape uses the same list.
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
 * Starting width of each default column, in CSS pixels, fitted to its content.
 * BUSINESS: at 1440 px, the width the "1 · Loan Tape" design board is drawn for, all
 *   12 default columns show without scrolling sideways while the explanation is
 *   closed (its default), and Loan ID through FICO still show with it open. Before
 *   Step 1g every column was 130 px and only about 6 fitted. ILLUSTRATIVE display
 *   choices, sized like the board's table: narrow for 3-digit FICO and 2-letter
 *   state, wide for seller names. A trader can still drag any column wider.
 * TECH: applied in buildColumnDefs (loanColumns.ts); a column not listed keeps the
 *   grid default (LoanGrid.tsx). The keys must be exactly api.toml's
 *   [columns] default_visible names; loanColumns.test.ts reads that file to check. The sum must stay within the grid's width at 1440 px
 *   with the explanation closed (about 1,150 px); Playwright checks it in a real
 *   browser (e2e/tests/loan-tape-layout.spec.ts).
 */
export const DEFAULT_COLUMN_WIDTHS: Readonly<Record<string, number>> = {
  loan_id: 92, seller: 173, program: 100, product: 94, state: 60, note_rate: 106,
  current_upb: 120, fico: 60, ltv: 72, dti: 72, dq_status: 86, occupancy: 100,
};

/**
 * Starting width of the two columns Product Slotting adds (Step 5b), in CSS pixels.
 * BUSINESS: wide enough for "GNMA II 30Y 3.0 / 3.5" and three story pills. They
 *   come after the tape's 12 default columns, so once the tape is slotted the grid
 *   scrolls sideways for them at 1440 px (a choice made in planning); the tape's
 *   own 12 still fit in the 1,150 px above. ILLUSTRATIVE display choices.
 * TECH: applied with DEFAULT_COLUMN_WIDTHS in buildColumnDefs; together their keys
 *   are exactly api.toml's default_visible names (loanColumns.test.ts).
 */
export const SLOT_COLUMN_WIDTHS: Readonly<Record<string, number>> = {
  slot: 160, spec_stories: 210,
};
