# Build log
One entry per step, newest first. Copy the template for each new step.

## Step 1d, the Loan Tape screen to the design board (2026-11-19)
- Built: the Loan Tape screen redone to the "1 · Loan Tape" board of the LoanIQ
  design canvas. A header with the logo, "Mortgage capital markets desk", the
  synthetic-data badge and a disabled "Ask the tape" box; a sidebar grouped Tape /
  Price / Trade / Showcase with every unbuilt screen disabled and tagged Planned;
  three summary panels (program mix in $M, note rate distribution in half-point
  buckets, MBA delinquency); six desk-question chips (LTV over 125, New York, Puerto
  Rico, 90+ / FC / REO / BK, Modified, Forbearance) that filter the grid in one click;
  a grid opening on 12 columns with a Columns picker for the rest; and the "Explain
  this screen" panel beside the grid with Business and Technical tabs, a glossary
  card and term chips. Back end: `/api/loans/breakdowns`, `/api/loans/questions`,
  `/api/tape`, and `?question=` on `/api/loans`, with the rules in
  `desk_questions.toml`.
- Desk problem it solves: in one screen a trader sees who can buy the tape, which
  coupons it fits, how much of it is late, and the loans that change the price or
  cannot be pooled, each one click from the grid.
- My key decisions: keep the six KPI tiles as a slim row; Export CSV disabled and
  Planned until there is a streaming export; fonts self-hosted with @fontsource; no
  change to the tape generator, so no as-of date or seed in the header yet.
- What Claude Code did: read the design canvas and compared it with the repo; proposed
  the plan and four open decisions; wrote the panel and desk-question API, the config,
  the screen's components, the content files and the tests; regenerated the OpenAPI
  spec and types; ran every layer. Along the way: the first screenshot showed the KPI
  tiles clipping the UPB value and the sidebar wrapping; both were fixed in CSS. Three
  new panel tests first compared bar widths as text ("100.0%"), but the browser
  writes "100%"; they now compare numbers. Existing tests changed where the
  requirement changed (badge text, "Planned" instead of "Step N", the explanation open
  by default with tabs), each checking the new behavior as strictly as before.
- What I changed after review:
- Tests and coverage: every layer passes through `test.ps1`. Back end: 184 tests
  (40 new, for the panels, bucket edges, desk-question loading and safety, the
  question filter and timing on 50,000 loans), coverage 98.8%. Front end: 82 Vitest
  tests (38 new). End to end: 13 Playwright tests (5 new) against the built app.
- My take:

## Step 1c, the single-page app and the loan grid (2026-11-18)
- Built: the LoanIQ single-page app in `frontend/` (Vite, React, TypeScript, React
  Router, AG Grid Community). A header with the synthetic-data badge and the row
  count for the current filter; a sidebar showing the whole workflow, with later
  screens marked by their step; the Loan Tape screen with six KPI tiles (Loans,
  Current UPB, WAC, WA FICO, WA LTV, Delinquent loans) and a dark, dense grid that
  pages the tape 100 loans at a time, sorting and filtering on the server. An
  "Explain this screen" panel and glossary tooltips on tiles and column headers.
  FastAPI now also serves the built app, and `test.ps1` and `start.ps1` run and gate
  every test layer.
- Desk problem it solves: a trader opens a tape and sees its headline numbers at once,
  then scrolls, sorts and filters every loan (largest balances, New York only,
  delinquent in red) without the browser ever holding the whole tape.
- My key decisions: the Infinite Row Model with server-side sort and filter; Playwright,
  `test.ps1` and `start.ps1` in this step, so it ends with every test layer running;
  header tooltips from the glossary through a column-to-term map in `content/`.
- What Claude Code did: proposed the plan and the two open decisions; wrote the SPA,
  the OpenAPI export and generated types, SPA serving in FastAPI, the screen
  explanation, the test scripts, the tests and the decision records; ran every layer.
  Along the way: the first Playwright run showed that unknown URLs hit React Router's
  default error page (now a "Screen not found" screen) and that AG Grid left
  off-screen columns out of the page (column virtualization now off, as a tape has
  ~41 columns). A Step 1b test caught that `httpx2` was missing from the virtual
  environment; `pip install -r requirements.txt` fixed it, and the test is unchanged.
- What I changed after review:
- Tests and coverage: every layer passes through `test.ps1`. Back end: 144 tests
  (12 new, for SPA serving, path safety and the OpenAPI export), coverage 98.5%.
  Front end: 44 Vitest tests (formats, query building, columns, datasource, content,
  tiles, explain panel, app shell). End to end: 8 Playwright tests in Chromium against
  the built app.
- My take:

## Step 1b, loan API (2026-11-18)
- Built: a FastAPI loan API (`backend/app/main.py`) over an in-memory DuckDB copy of
  the tape: `/api/health`, `/api/loans/columns`, `/api/loans` (paged, sorted and
  filtered on the server) and `/api/loans/summary` (count, total current UPB, WAC,
  WA FICO, WA LTV, delinquent loans). A safe SQL builder for AG Grid filters
  (`backend/app/loan_query.py`), limits in `api.toml`, column labels in
  `content/loan-columns.json`.
- Desk problem it solves: a trader can slice a seller tape of any size ("LTV over
  125", "largest balance first", "New York only") and get the headline numbers they
  quote for a pool, without the browser holding every loan.
- My key decisions: server-side paging, sorting and filtering in DuckDB; a hard cap
  of 500 rows per page; money as JSON numbers; delinquent means any status other
  than Current; column labels as content, not code; a 300 ms budget for one page of
  a 50,000-loan tape.
- What Claude Code did: proposed the plan and the open questions (summary filter,
  where labels live, the delinquency definition); wrote the API, the SQL builder,
  the config, the labels, 59 API tests and the decision records; ran the tests and
  timed a page.
- What I changed after review: set the glossary's LTV formula to (loan amount /
  appraised property value) x 100, matching the schema and the generator; switched
  the TestClient's HTTP package from the deprecated httpx to httpx2.
- Tests and coverage: 132 back-end tests pass (60 new API tests, including SQL
  injection attempts, unknown columns and a 50,000-loan timing test; a deep sorted
  page takes about 150 ms against the 300 ms budget); coverage 98%, with
  `main.py` and `loan_query.py` at 100%.
- My take:

## Step 1a, synthetic loan tape generator (2026-11-18)
- Built: `python -m app.loan_tape_gen`, which writes a seeded synthetic loan tape
  (2,000 loans by default, 41 fields) to data/loan_tape.parquet and .csv. Also its
  config file, a schema document with a pipeline diagram, the spec-story rules
  (spec_stories.toml) with a validator that only accepts safe SQL, and the tests.
- Desk problem it solves: every later screen needs a realistic tape to work on.
  Program-specific credit, rates that follow the vintage, delinquency driven by
  risk, and guaranteed "story" loans (LLB tiers, NY, PR, LTV over 125, ARMs about to
  reset, 90+, FC and REO).
- My key decisions: a fixed as-of date instead of today; money computed in float but
  stored as Decimal and checked against an exact schedule; LTV over 125 modeled as
  HARP-era refinances; SOFR ARMs from 2021 with three cap columns; pytest-cov now and
  test.ps1 later; Jumbo and High-Balance without county limits.
- What Claude Code did: proposed the six-step pipeline and the open decisions; wrote
  the generator, config, tests, schema doc, glossary entries, sources and decision
  records; ran the tests.
- What I changed after review: renamed tapegen to loan_tape_gen everywhere; made
  `--n 2000 --seed 42` the defaults; asked for the county-limit simplification to be
  recorded; asked for a Mermaid diagram at the top of the schema doc. Then, to finish
  the step: switched the base-rate source to FHFA's National Mortgage Database
  (with MBA weekly readings for 2026); spotted that one rate per
  year flattened 2022, so base rates are now by origination month; supplied the
  public sources for the LLB, Puerto Rico, FICO and New York stories; and asked for
  spec stories as validated SQL rules in spec_stories.toml, so a new tier is one
  number in config.
- Tests and coverage: 72 back-end tests pass (38 generator, 34 spec stories,
  including DuckDB coverage checks and unsafe-rule rejections); coverage 98%.
- My take: A loan tape is only as useful as the stories in it, so I treated spec stories
  as desk rules, not code: each is a SQL condition per product, checked for safety
  when it loads, and a new LLB tier is one number in config. Claude Code wrote the
  generator quickly; my job was the judgment calls (which tiers, which public
  sources, what counts as 90+ days delinquent) and checking the results.

## Template: Step N, title (date)
- Built:
- Desk problem it solves:
- My key decisions:
- What Claude Code did:
- What I changed after review:
- Tests and coverage:
- My take:A trader slicing a seller’s tape shouldn’t have to wait on the screen, and the browser shouldn’t hold every loan. So the server does the paging, sorting, filtering and pool math in DuckDB, and no page can be bigger than 500 rows. The definitions matter as much as the speed: delinquent means any status other than Current, so the summary count is the conservative number a desk would quote, and I corrected the glossary’s LTV formula to match the tape. Claude Code wrote the API and 60 tests quickly, including SQL injection attempts. My part was setting the limits and the 300 ms budget (a deep page of a 50,000-loan tape comes back in about 150 ms) and checking that each number means what a desk expects.
