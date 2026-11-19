# Decisions
One entry per design decision, newest first.

## 2026-11-18: Loan API sorts, filters and pages in DuckDB SQL
Decision: `backend/app/main.py` loads the tape into an in-memory DuckDB table `loans`
at start-up (generating the default tape if `data/loan_tape.parquet` is missing).
`backend/app/loan_query.py` turns the grid's sort string and AG Grid filter model into
SQL. Column names are checked against `DESCRIBE loans` and quoted; every value is a `?`
parameter. Supported filters: text contains/equals (case-insensitive, as in AG Grid),
number equals/greaterThan/lessThan/inRange (inclusive), and AG Grid's AND/OR
two-condition form. Anything else is HTTP 400. `loan_id` is always the last sort key.
Page size limits and the timing budget live in `backend/app/config/api.toml`.
Why: the browser never holds the whole tape, so the server must answer every slice
correctly; refusing unknown filters is safer than guessing. The tie-break keeps pages
stable when many loans share a sort value (FICO, state).
Alternative considered: load the whole tape into the browser and let the grid sort
it. Simple at 2,000 loans, but not at a 50,000-loan seller tape.

## 2026-11-18: Money returned as JSON numbers
Decision: DECIMAL(14,2) columns are cast to DOUBLE in the grid query, so the JSON has
numbers, not strings. Summary totals are summed in DECIMAL in DuckDB, then sent as a
number.
Why: the grid needs numbers to sort and format. A double holds any 2-decimal amount
under $1 trillion closely enough to round-trip to the same cents; a test checks every
money field against the stored Decimal.

## 2026-11-18: Delinquent means any MBA status other than Current
Decision: the API summary counts a loan as delinquent when `dq_status <> 'Current'`,
so 30, 60, 90, 120+, FC, BK and REO all count. This matches the generator's printout.
Why: one definition across the app. A "30+ days only" count would hide the loans in
foreclosure, bankruptcy or REO, which are the most serious.

## 2026-11-18: Column labels live in content/
Decision: readable column headers are in `content/loan-columns.json` (labels only) and
served by `GET /api/loans/columns`. Field meanings stay in
`docs/domain/loan-tape-schema.md` and terms in `content/glossary.json`.
Why: headers are visitor-facing words, and those live in content/. A test keeps the
label list equal to the tape's column list.

## 2026-11-18: Spec stories are validated SQL rules in config
Decision: each spec-pool story is a `[[story]]` in `backend/app/config/spec_stories.toml`
with a name, a product list and `where`, a SQL true/false test over tape columns. A story
can list `tiers` with a `{cap}` placeholder, and one story is made per cap (LLB_85K and so
on), so a new tier is one new number. `backend/app/spec_stories.py` parses every `where`
with sqlglot when the config loads. It allows only tape columns, comparisons,
AND/OR/NOT, IN, BETWEEN, parentheses and literals, and refuses semicolons and comments
up front. The SQL used later is sqlglot's re-rendering of the checked tree. The tape
generator reads the tiers and states from this file; `loan_tape_gen.toml` keeps only
the minimum counts (`[coverage.stories]`). It can force only two rule shapes,
`orig_upb <= {cap}` and `state = '..'`, and treats a minimum on any other story as an
error. Tier minimums apply per band between caps. The slotting engine that uses the
stories is Step 5.
Why: the desk adds and changes stories often, so the rules are data in one place.
They are still SQL, so they are treated as code: the allowlist stops subqueries,
functions, second statements and unknown columns before anything reaches DuckDB.
Alternative considered: hand-written Python filters per story. Safer by default, but
every new story or tier would need a code change.

## 2026-11-18: Base note rate by origination month, from FHFA NMDB
Decision: the base rate is a monthly table, `base_rate_30y_by_month`, so loans follow
the market within a year (2022 rises from about 3.2% to 6.4%). The 2015-2025 values
come from FHFA's National Mortgage Database (Conventional Conforming Market, average
contract rate at origination, count-weighted). 2026 is not in NMDB yet; it is a
straight line through four MBA Weekly Applications Survey readings. All approximate
and illustrative.
Why: one rate per year gave a January 2022 loan the same rate as an October 2022
loan, which a desk would spot at once. MBA's history is subscriber-only and Fannie
Mae's performance data needs a login, so NMDB is the public source that could be
confirmed. NMDB averages all terms and lags market quotes by the lock-to-close
period, which is acceptable for an approximation.

## 2026-11-18: Jumbo and High-Balance without county limits
Decision: loan limits use only the FHFA one-unit baseline for each year and the 150%
high-cost ceiling. There are no county-level limits. Jumbo means above the 2026
baseline ($832,750) in every vintage; High-Balance means between the year's baseline
and the ceiling.
Why: county limits add a lookup table of about 3,000 counties without changing the
workflow LoanIQ demonstrates.
Consequence: a loan we call Jumbo whose balance is between the baseline and the
high-cost ceiling would be a conforming High-Balance loan in a high-cost county.
Likewise, a loan we call High-Balance would be Jumbo in a county whose limit is the
baseline. Slotting (Step 5) inherits this simplification.

## 2026-11-18: Fixed as-of date for the loan tape
Decision: the generator takes `--as-of` (default in config, 2026-11-01), which must be
the 1st of a month. Loan age, delinquency and "ARM reset in the next 6 months" are
measured from it.
Why: using today's date would make the same seed give a different tape tomorrow.
Tapes are cut at month boundaries.

## 2026-11-18: Money computed in float, stored as Decimal
Decision: amortization is calculated in vectorized float64 and rounded to cents.
Money is written to Parquet as Decimal(14,2). A test checks the float results against
an exact 50-digit Decimal month-by-month schedule, to within a cent.
Why: it is fast enough for large tapes (50,000 loans in under a second) and exact to
the cent where it matters, in storage and in DuckDB totals.
Alternative considered: a Decimal loop for every loan. Exact, but it would not scale.

## 2026-11-18: LTV above 125 comes from high-LTV refinances
Decision: the coverage minimum "LTV > 125" applies to original LTV. Those loans are
Conventional rate/term refinances from 2015-2018, the HARP era of FHFA's high-LTV
refinance programs, with no second liens.
Why: no standard purchase program allows original LTV above 125. HARP is the public
program that did. MTM LTV above 100 arises on its own from home prices.

## 2026-11-18: ARMs are 2021+ SOFR ARMs with caps in three columns
Decision: 5/6, 7/6 and 10/6 ARMs exist only from 2021 and are indexed to 30-day
average SOFR. Caps are stored as initial_cap, periodic_cap and lifetime_cap rather
than one "2/1/5" text field. current_upb uses the start rate throughout, ignoring
resets that have already happened.
Why: agency SOFR ARMs started in 2021, after LIBOR was retired. Three numeric columns
are easy to filter and sort. Recasting balances at each reset adds index history
without helping the workflow.

## 2026-11-18: Delinquent balances stop at the last paid installment
Decision: current_upb is the scheduled balance after loan_age minus missed payments.
Why: that is how a servicer reports it. A loan 90 days late has not paid down three
months of principal.

## 2026-11-18: Coverage forced before deriving fields
Decision: the generator samples drivers, forces coverage minimums by editing drivers,
then derives every other field once. Delinquency minimums are met by moving the
riskiest current loans that are old enough.
Why: derived fields (rate, payment, balance, LTV family) can never be stale, and forced
delinquency still follows credit quality.
Interpretation: the "90+" minimum counts the 90 and 120+ buckets; FC and REO have
their own minimums.

## 2026-11-18: Coverage tooling now, test.ps1 later
Decision: pytest-cov is in requirements.txt from Step 1a. Until test.ps1 exists, tests
run with `.venv\Scripts\python.exe -m pytest --cov=app` from backend/. test.ps1 arrives
with the front end.
Why: the 80% coverage rule needs a measurement from the first back-end step.

## 2026-11-18: Business rules come from public sources
Decision: every business rule, threshold and price grid traces to a public industry source,
recorded in docs/public-sources.md, and every number is labeled illustrative.
Why: anyone can check where a rule came from, and the app stays generic.

## 2026-11-18: Visitor-facing words live in content/
Decision: the About page, screen explanations, glossary and build log are Markdown and JSON
files in content/, rendered by the app.
Why: one fact in one place. Claude Code and the app read the same text.
Alternative considered: text hard-coded in React components.

## 2026-11-17: Synthetic data only
Decision: every loan is generated from a seed. No real borrowers.
Why: the app is public, and a seed makes every demo repeatable.

## 2026-11-17: Stack
Decision: Python, FastAPI and DuckDB back end; React single-page app front end.
Why: a common fintech pairing, and DuckDB gives fast SQL with no database server.
