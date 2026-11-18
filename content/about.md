# About LoanIQ

## What LoanIQ does
LoanIQ follows a mortgage capital markets desk's workflow. A loan tape comes in, each loan
is slotted into the pools it could join, best execution prices every option, positions are
monitored, and an optimizer turns the loans into pool candidates.

## The approach
- Start from the desk's real workflow and build it one step at a time.
- Synthetic data only, generated from a seed, so every demo is repeatable.
- Business rules from public industry sources, with illustrative numbers.
- Every screen explains itself, in business and technical terms.
- Tests gate every change.

## Architecture
The loan tape is stored in Parquet and queried in DuckDB. A FastAPI back end serves it to
this React single-page app.

## What's next
See the roadmap on the How it was built page.
