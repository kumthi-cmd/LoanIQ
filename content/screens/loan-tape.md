## Business
The Loan Tape screen is the desk's first look at a pool of loans offered by a seller.
Before anyone talks about price, a trader wants to know what is in the tape.

The row of headline numbers is what a trader quotes first:
- **Loans** and **Current UPB**: how big the tape is, by count and by unpaid balance.
- **WAC**: the weighted-average note rate. It decides which agency coupons the loans
  can be pooled into.
- **WA FICO** and **WA LTV**: the average credit and leverage. Higher FICO and lower
  LTV usually mean a better price.
- **Delinquent loans**: loans that are not Current. They price lower and usually
  cannot go into an agency pool, so the desk finds them first.

Averages are weighted by current UPB, so large loans count for more.

The three panels show the tape's shape:
- **Program mix**: balance by program. The program decides who can buy a loan:
  the GSEs for Conventional and High-Balance, Ginnie Mae for FHA, VA and USDA,
  banks and private investors for Jumbo and Non-QM.
- **Note rate distribution**: balance in half-point buckets. One WAC can hide two
  clusters of coupons that trade into very different TBA securities.
- **MBA delinquency**: how many loans are Current, and how many are in each late
  status, from 30 days to foreclosure, REO and bankruptcy.

The **desk questions** are the questions a trader asks of every new tape: LTV over
125, New York, Puerto Rico, 90 days late or worse, modified, in forbearance. Each chip
shows how many loans answer it; click it to see exactly those loans in the grid, and
click again for the whole tape. The headline numbers, panels and chip counts always
cover the whole tape; the grid and the header count follow the chip and any column
filters.

The grid opens on the fields a trader reads first; **Columns** adds any of the
others. Sort and filter any column: the largest balances, FICO under 680, every loan
in a state. Delinquency status is shown in red unless the loan is Current. Hover a
term or a column header to read its definition.

All loans are synthetic, and every number and threshold is illustrative.

## Technical
When the screen opens it makes five calls at once: `/api/loans/columns` for the
column list, `/api/loans/summary` for the headline numbers, `/api/loans/breakdowns`
for the three panels, `/api/loans/questions` for the chip counts and `/api/tape` for
the field and seller counts. Each panel is one GROUP BY over an in-memory DuckDB copy
of the tape, so even a 50,000-loan tape answers in milliseconds. The note-rate bucket
width and the order of the delinquency statuses are settings in the API's config,
not in the screen.

The grid is AG Grid Community with the Infinite Row Model: it asks `/api/loans` for
100 loans at a time as you scroll, so a tape of any size scrolls the same. Sorting
and filtering never happen in the browser. The grid's sort and filter model is sent
as query parameters, and FastAPI turns it into parameterized SQL. Column names are
checked against the real column list, so nothing typed into a filter can change the
query.

A desk question travels as an id, such as `?question=ltv_over_125`, never as SQL. The
rules live in a config file (`desk_questions.toml`) and are checked when the API
starts by the same SQL allowlist as the spec-pool stories: tape columns, comparisons,
AND, OR, IN and literals only. The server joins the chosen rule and the grid's
filters with AND, so the chip count and the grid's total always agree.

Columns come from the API, so a new tape field appears without a front-end change.
Formatting is display only: money with commas and no cents, rates with 3 decimals,
LTV and DTI with 2, balances in the panels in $ millions. The TypeScript types for the
API's data are generated from FastAPI's OpenAPI spec, so a renamed field breaks the
build instead of showing a blank panel. Every term comes from the shared glossary,
and this text comes from a Markdown file, not from the code.
