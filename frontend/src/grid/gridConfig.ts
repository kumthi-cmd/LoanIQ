/**
 * grid/gridConfig.ts: the loan grid's paging and tooltip settings, in one place.
 *
 * BUSINESS: how many loans the grid fetches per request and how many it keeps in
 *   memory. ILLUSTRATIVE engineering choices, not industry rules.
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
