# Decisions
One entry per design decision, newest first.

## 2026-11-20: Host LoanIQ as one Docker container on Render, tested by GitHub Actions
Decision: LoanIQ goes online as one service, built from one `Dockerfile` and deployed
on Render with a Blueprint (`render.yaml`):
- One container: FastAPI serves the built SPA at `/` and the API at `/api`, exactly as
  `start.ps1` and the Playwright tests run it.
- The seeded tape is generated when the image is built, with the generator's defaults.
- The container runs as a non-root user and listens on `$PORT`.
- GitHub Actions (`.github/workflows/ci.yml`) runs every `test.ps1` layer, then builds
  and smoke-tests the image. Render deploys `main` only after those checks pass
  (`autoDeployTrigger: checksPass`) and its health check (`/api/health`) answers.
- Free plan while building, Starter before the link goes on any application.
- The Node major version lives in `.nvmrc`, read by CI and checked against the
  Dockerfile by a test. A test also fails if `ci.yml` and `test.ps1` drift apart.
- CI runs on every push and on pull requests into `main`, not on every pull request.
- One `requirements.txt`, so the image also holds the test tools (a few MB).
Why:
- One domain, no CORS, and the Step 4 Claude API key stays on the server, never in
  the browser.
- Production runs the same way the tests do, so a green test run means what it says.
- A container keeps us portable: only `render.yaml` is Render-specific.
- I have no Docker on my PC, so GitHub Actions builds and tests the image on every
  push. The repo is private (2,000 Actions minutes a month), so CI is kept lean:
  one Linux runner, Chromium only, caches, reports only on failure, older runs
  cancelled. A run takes about 2 minutes, about 3 billed minutes.
- Generating the tape at build time keeps `data/` out of Git, gives every deploy the
  same loans, and keeps start-up fast.
Alternatives considered:
- Vercel for the SPA plus Render for the API: two services and two addresses, CORS
  between them, and two deploys to keep in step for every change.
- DigitalOcean App Platform: runs the same container, but has no free tier for an
  app with a server.
- Google Cloud Run: scales to zero and has a free allowance, but needs a Google Cloud
  project, billing, a container registry and access settings before the first deploy.
  A good next home if traffic grows, with no change to the Dockerfile.
- AWS Lightsail containers: simple pricing, but no lasting free tier and more AWS
  setup than Render.
- Self-hosting on my PC through a Cloudflare Tunnel: free, but the site is down
  whenever the laptop sleeps or travels, and it puts a public service on my own
  machine.

## 2026-11-19: The header shows a 48 px logo with a bold "LABS"
Decision: the header shows brand/logo/loaniq-labs_horizontal_dark-bg_48px.svg at
48 px high, a version of the logo drawn for that size. "LABS" is bold, 12 px,
#D3DEEC and followed by a gold rule. "LoanIQ" is 30 px Space Grotesk Bold, outlined
in the SVG. The flask and brain are simpler, with thicker strokes. The v1 file stays in
brand/ for the other uses the README lists.
Why: in the v1 logo at 36 px, "LABS" (Montserrat Regular, tracked wide, Slate #9FB3CC)
was too thin to read. The new SVG is 48 px high, so the header shows it at its natural
size with no scaling.
Alternatives considered: keeping the v1 artwork and only making it bigger; redrawing
only "LABS" in the v1 Montserrat style.
Note: this file's lettering (Space Grotesk) and "LABS" colour (#D3DEEC) differ from
the README's TYPE and COLOURS (Montserrat; Slate #9FB3CC). The brand tokens in
styles.css still follow the README. The rest of the kit (favicons, stacked and light
logos) is v1 until it is redrawn.

## 2026-11-19: The LoanIQ Labs brand comes from brand/, unchanged
Decision: brand/ is the only copy of the logo kit. The build publishes from it and
nothing is copied into frontend/:
- brand/icon/ appears at /icon/ with fixed names, through a small Vite plugin
  (frontend/src/build/brandIcons.ts). Favicons need unhashed URLs, because
  index.html and the web manifest name them directly.
- The header logo (logo/loaniq-labs_horizontal_dark-bg.svg) is imported through an
  "@brand" alias, like "@content", so Vite publishes only that file, with a hashed name.
- The web manifest is app metadata, not artwork, so it lives in frontend/public/.
- The header shows the logo inside the page's <h1>, alt text "LoanIQ Labs". The tab
  title is "LoanIQ · LoanIQ Labs".
- The brand colours are CSS tokens (--brand-*), checked against brand/README.txt by
  a test. The page keeps the design board's palette, and Neural Gold appears only in
  the logo. Every accent on the board already has a meaning (blue = interactive or
  selected, amber = the synthetic-data warning), and gold beside the amber badge
  would blur the warning (.claude/rules/frontend.md: color only for meaning).
Why: one copy of the artwork means a new version of the kit reaches the app with no
copying. Keeping colour for meaning keeps the warning unmistakable.
Alternatives considered: Vite's publicDir pointed at brand/ (it would also publish the
README and the 3200 px brand sheet); copying the icons into frontend/public (two
copies that drift); a gold accent for the current screen or primary buttons.
Note: the README's Amber (#D49A00) on white is 2.5:1, below WCAG AA for text. It
matters only if a light page is ever added.

## 2026-11-19: The Loan Tape screen follows the "1 · Loan Tape" design board
Decision: the screen matches the LoanIQ design canvas: a dark desk layout, a header
with the synthetic-data badge and a disabled "Ask the tape" box, a sidebar grouped
Tape / Price / Trade / Showcase where every screen not built yet is visible, disabled
and tagged "Planned" (this replaces the greyed "Step N" tag), three summary panels,
desk-question chips, and the explanation open beside the grid with Business and
Technical tabs. The six KPI tiles stay, as one slim row above the panels. Export CSV
is shown disabled and tagged Planned. The design's sample numbers are not used:
every number comes from the API.
Why: the board is the agreed look; the KPI tiles keep WAC, WA FICO and WA LTV on
screen, which the explanation talks about. A correct CSV export of a server-paged
grid needs its own streaming endpoint, so it waits.

## 2026-11-19: Desk questions are validated SQL rules in config, sent as ids
Decision: the chips' rules live in `backend/app/config/desk_questions.toml` and are
checked at start-up by the same sqlglot allowlist as the spec stories
(`spec_stories.validate_where`). The browser sends `?question=<id>`; the server
looks the id up and ANDs the rule with the grid's filter. An unknown id is a 400. A
bad rule stops the API from starting. Chip labels live in
`content/desk-questions.json`; a test checks both files list the same ids in order.
One chip is on at a time.
Why: "status is one of five values" and "flag is true" cannot be expressed with the
grid's Community filters, and the browser must never send SQL. One question at a time
keeps the chip count and the header count telling the same story.
Alternative considered: new set and boolean filter types in `loan_query.py`. More
general, but the chips would then depend on the grid's filter UI, which cannot show
them.

## 2026-11-19: Summary panels cover the whole tape, from one GROUP BY each
Decision: `/api/loans/breakdowns` returns current UPB by program, by note-rate bucket
and loans by MBA status, and `/api/loans/questions` the chip counts, all over the
whole tape, like the KPI tiles. Buckets are 0.5 points wide from 2.0% to 9.0%+, with
the first bucket open below and the last open above, and every bucket present (0
when empty); statuses follow `dq_status_order`. Both are settings in `api.toml`
[breakdowns], labelled illustrative. `/api/tape` gives the field and seller counts.
Why: the panels describe the tape the seller sent; filtering them with the grid would
change the meaning of each number as the trader types. Open ends mean no loan's
balance is ever left off the chart.

## 2026-11-19: The grid opens on 12 default columns; a Columns picker shows the rest
Decision: the grid shows loan ID, seller, program, product, state, note rate,
current UPB, FICO, LTV, DTI, DQ status and occupancy (`DEFAULT_VISIBLE_COLUMNS` in
`frontend/src/grid/gridConfig.ts`). The "Columns" button lists every tape field as a
checkbox. Loan ID is always shown.
Why: the fields a trader reads first, as on the design board. AG Grid's column tool
panel is an Enterprise feature, so the picker is a small component of our own.

## 2026-11-19: Fonts are self-hosted with @fontsource
Decision: Inter and JetBrains Mono come from the `@fontsource/inter` and
`@fontsource/jetbrains-mono` npm packages (5.3.0), imported in `main.tsx`.
Why: no request to an outside font service, and the same look offline and in tests.
Alternative considered: a Google Fonts link in `index.html`. Simpler, but a
third-party request on every visit.

## 2026-11-19: No tape as-of date or seed in the header, for now
Decision: the header does not show "Tape as of ... · seed ...". The tape file does
not record them, and the generator was left unchanged.
Why: showing the config defaults would be a guess, wrong for any tape built with
other settings. Adding them means writing them into the Parquet file's metadata in
the generator, a later decision.

## 2026-11-18: The SPA is Vite, React, TypeScript, React Router and AG Grid Community
Decision: the front end in `frontend/` uses Vite, React 19, TypeScript, React Router
(a layout route with a sidebar; screens swap inside it with no reload) and AG Grid
Community 36 with `AllCommunityModule` registered once in `main.tsx`. The left sidebar
lists every workflow screen from `frontend/src/nav.ts`; screens not built yet are
greyed out with their roadmap step. Unknown URLs show a "Screen not found" screen.
Why: the stack named in `.claude/rules/frontend.md`; one list for the sidebar shows
the whole workflow from the first screen.

## 2026-11-18: The loan grid uses AG Grid's Infinite Row Model with server-side sort and filter
Decision: the grid asks `/api/loans` for blocks of 100 loans as the user scrolls and
keeps at most 20 blocks (settings in `frontend/src/grid/gridConfig.ts`). Sorting and
filtering are always sent to the server; the grid offers only the filters the API
accepts (text contains/equals; number equals/greater than/less than/between). Date
and yes/no columns are sortable but not filterable until the API supports them.
Floating filter boxes sit under each header. Columns are not virtualized, so every
header and filter box is in the page.
Why: the browser never holds the whole tape, and every answer covers the whole tape.
Offering a filter the server refuses would only produce errors. A tape has a fixed
~41 columns, so drawing them all is cheap and helps keyboard users, screen readers
and Playwright.
Alternative considered: the Client-Side Row Model (load every loan into the
browser). Simpler, but it does not scale to large tapes.

## 2026-11-18: Front-end API types are generated from the OpenAPI spec
Decision: `python -m app.export_openapi` writes `frontend/src/api/openapi.json`, and
`npm run gen:api` (openapi-typescript) turns it into `schema.d.ts`. Both are committed.
A back-end test fails if the committed spec differs from the live API.
Why: no hand-written copies of API types (`.claude/rules/frontend.md`); a renamed
field breaks the build instead of showing a blank tile.

## 2026-11-18: FastAPI serves the built SPA; one port in production and in tests
Decision: `backend/app/main.py` serves `frontend/dist` at `/`. Real files are served
as is; any other non-API path returns `index.html` so screen URLs can be reloaded;
unknown `/api/...` paths stay JSON 404s. In dev mode Vite serves the SPA on port 5173
and proxies `/api` to port 8000.
Why: Playwright tests the built app at http://localhost:8000 (`.claude/rules/testing.md`)
with no second server and no CORS setup.

## 2026-11-18: Column header tooltips map columns to glossary terms in content/
Decision: `content/loan-columns.json` gains a `terms` map (column -> glossary term).
The SPA shows that term's definition and "why it matters" as the header tooltip.
KPI tile labels use the same glossary tooltips.
Why: one definition per term, in `content/glossary.json`; the map holds only names.

## 2026-11-18: test.ps1 runs every layer; start.ps1 starts only after it passes
Decision: `test.ps1` runs pytest with coverage (80% minimum), the TypeScript type
check, Vitest, the production build and Playwright, stopping at the first failure.
Pass or fail is decided by exit codes only. `start.ps1` runs it before starting uvicorn.
Why: the testing rule. Exit codes, because Windows PowerShell 5.1 treats tools'
stderr warnings as errors.

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
