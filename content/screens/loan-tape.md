## Business
The Loan Tape screen is the desk's first look at a pool of loans offered by a seller.
Before anyone talks about price, a trader wants to know what is in the tape.

The tiles across the top are the numbers a trader quotes first:
- **Loans** and **Current UPB**: how big the tape is, by count and by unpaid balance.
- **WAC**: the weighted-average note rate. It decides which agency coupons the loans
  can be pooled into.
- **WA FICO** and **WA LTV**: the average credit and leverage. Higher FICO and lower
  LTV usually mean a better price.
- **Delinquent loans**: loans that are not Current. They price lower and usually
  cannot go into an agency pool, so the desk finds them first.

The averages are weighted by current UPB, so large loans count for more, and they
cover the whole tape, not just the rows the grid is showing.

The grid shows every loan. Sorting and filtering answer the desk's everyday
questions: the largest balances, every loan with LTV above 125, everything in New
York, every loan 90 days or more past due. The header shows how many loans match.
Delinquency status is shown in red unless the loan is Current. Hover a column header
or a tile label to read the term's definition.

All loans are synthetic, and every number is illustrative.

## Technical
The screen makes two calls when it opens: `/api/loans/columns` for the column list
and `/api/loans/summary` for the tiles. The grid is AG Grid Community with the
Infinite Row Model: it asks `/api/loans` for 100 loans at a time as you scroll and
keeps a limited number of blocks in memory, so a tape of any size scrolls the same.

Sorting and filtering never happen in the browser. The grid's sort and filter
model is sent to the server as query parameters, and FastAPI turns it into
parameterized SQL over an in-memory DuckDB copy of the tape. Column names are
checked against the real column list, so nothing typed into a filter can change
the query. Text columns offer "contains" and "equals"; number columns offer equals,
greater than, less than and between. Date and yes/no columns can be sorted but not
yet filtered, because the API does not accept those filters yet.

Columns come from the API, so a new tape field appears without a front-end change.
Formatting is display only: money with commas and no cents, rates with 3 decimals,
LTV and DTI with 2, dates as YYYY-MM-DD, with numbers right-aligned in tabular
figures. The TypeScript types for the API's data are generated from FastAPI's
OpenAPI spec, so a renamed field breaks the build instead of showing a blank tile.
Every term's definition comes from the shared glossary, and this text comes from a
Markdown file, not from the code.
