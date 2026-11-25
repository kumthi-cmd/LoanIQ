## Business
Product Slotting answers "where can this loan go?" before the desk prices a tape. For every
loan it checks three things in order: does its program have an agency pool (UMBS for
conventional loans, GNMA II for FHA, VA and USDA), does its product trade as a TBA coupon
(30-, 20- and 15-year fixed), and is it current. A loan that fails a check is not slotted,
and the first check it failed is the reason.

Each slotted loan gets two pool coupons from its note rate, a down coupon and an up coupon
one step higher, and every spec story it qualifies for: low loan balance tiers (the lowest
tier it fits), New York, Puerto Rico and low FICO. A loan with no story is generic TBA.

A loan can fit several stories but goes into one pool, so pay-ups never stack. Best
Execution (next) prices each slot and picks the highest all-in price. Every rule and the
coupon strip are illustrative.

## Technical
Product Slotting is an action on the Loan Tape, not a screen of its own. The sidebar
button and the Slotting panel open the run dialog. `POST /api/slotting/run` slots the
whole tape in one DuckDB pass, then streams one server-sent event per step with real counts
and a done event with the totals. The server never pauses; the dialog shows one line at a
time so a visitor can read it.

The rules live in `backend/app/config/slotting.toml` and `spec_stories.toml`, checked when
the server starts. The result is shared by every visitor and lives in memory, behind a lock
so two runs cannot overlap. Once it exists, `/api/loans` adds the Slot and Spec Stories
columns, which sort and filter in DuckDB like any other, and hovering a loan ID fetches
`GET /api/loans/{loan_id}/slots` for the card.
