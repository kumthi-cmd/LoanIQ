# Build log
One entry per step, newest first. Copy the template for each new step.

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
