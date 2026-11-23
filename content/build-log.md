# Build log
One entry per step, newest first. Copy the template for each new step.

## Step 1f, About and How it was built (2026-11-23)
- Built: the two Showcase pages, now live in the sidebar. About shows the stacked
  LoanIQ Labs logo above `content/about.md`. How it was built shows
  `content/how-it-was-built.md`, then "By the numbers" (back-end, front-end and
  end-to-end test counts, back-end coverage, commits and the date of the last full
  test run), then this build log. After every layer passes, `test.ps1` now writes those
  numbers to `content/build-facts.json`, which is committed so the live site at
  https://www.loaniqlabs.com shows them.
- Desk problem it solves: a capital markets or technology reader can see what LoanIQ
  is, how it was built AI-first, and the evidence behind "tests gate every change",
  without opening the repo.
- My key decisions: write the facts from a green local run and commit them, instead of
  having CI write to the repo; keep it a plain function, not a sixth test layer, so
  CI and `test.ps1` still match; get the counts without running the tests again; show
  a dash for any missing number; no Explain panel on these two pages, because each
  page is itself the explanation. Reasons: docs/decisions.md.
- What Claude Code did: proposed the plan and the trade-offs (the commit count is
  one behind, and the file changes on most runs); built the two screens, a shared
  Markdown renderer that keeps the header logo as the page's only top-level heading,
  and the "By the numbers" tiles; wrote `Write-BuildFacts` in `test.ps1`; added the
  tests; updated the architecture, decisions and roadmap. Along the way: `vitest list`
  counted 91 front-end tests against 104 that really ran, because it lists an
  `it.each` table as one test. Rather than show a wrong number, the Vitest layer now
  also writes a JSON summary as it runs, and `test.ps1` reads the total from it. The
  layer's command did not change. While fixing the "planned screens" browser test for
  About, it also switched that test to find sidebar items by role and visible text,
  an open follow-up from Step 1d.
- What I changed after review:
- Tests and coverage: every layer passes through `test.ps1`. Back end: 232 tests (6
  new: the committed facts file and how `test.ps1` writes it, plus front-end test
  output kept out of the image), coverage 98.8%. Front end: 117 Vitest tests (13 new:
  every live sidebar route renders its own screen, the About logo and text, the How it
  was built page order, the facts tiles with full and missing numbers, and the facts
  parser; 1 updated, the sidebar's live links). End to end: 16 Playwright tests (2
  new: About and How it was built opened from the sidebar; 1 updated, the planned
  screens list without About).
- My take:

## Hosting, LoanIQ online: container, CI and Render (2026-11-20)
- Built: a `Dockerfile` that builds the screens with Node and runs them with the API
  on Python 3.12, as one container, with the seeded tape generated inside the image
  and the server running as a non-root user on the host's `$PORT`; a `.dockerignore`
  that keeps secrets and local files out; `.nvmrc` holding the Node version once; a
  GitHub Actions workflow that runs every `test.ps1` layer on each push, then builds
  the image, starts it and checks the tape and the screens; and `render.yaml`, a
  Render Blueprint that deploys `main` only after those checks pass.
- Desk problem it solves: anyone can open LoanIQ from a link, and what they see has
  always passed every test, on a clean machine, in the exact container that serves
  it. From now on every step goes live on push.
- My key decisions: one container on Render instead of Vercel plus Render, so one
  address, no CORS and the Claude key stays on the server; keep the container
  portable so only `render.yaml` is Render-specific; GitHub Actions builds the image
  because I have no Docker locally; keep CI lean for a private repo's minutes; free
  plan now, Starter before the link goes on an application; Hosting before the About
  page. Alternatives and reasons: docs/decisions.md.
- What Claude Code did: ran `test.ps1`, fast-forwarded `main` and made the `hosting`
  branch; wrote the Dockerfile, `.dockerignore`, CI workflow and Blueprint, each
  commented for business and tech; wrote `test_deploy_config.py`, 42 checks that read
  those files without Docker, including one that fails if `ci.yml` and `test.ps1` stop
  running the same layers in the same order; watched the CI runs with `gh`; updated
  the architecture, decisions, roadmap and How it was built pages. Along the way: a
  timing test on the 50,000-loan tape failed locally at about 360 ms against its
  300 ms budget. Nothing in the app had changed; the Surface was on battery, which
  slows the CPU (the back-end tests took 77 s instead of 12 s). Plugged in, it passed,
  and it passes on GitHub's runner. The budget did not change.
- What I changed after review: CI runs on every push and on pull requests into `main`
  only, so a branch is not tested twice for every PR; added the deployment-file checks
  and the How it was built paragraph; asked for ✅ and ❌ on every result, now in
  CLAUDE.md; closed Chrome and plugged in the laptop to find the timing failure's cause.
- Tests and coverage: every layer passes through `test.ps1` and in CI. Back end: 226
  tests (42 new, in `test_deploy_config.py`), coverage 98.8%. Front end: 104 Vitest
  tests (no change). End to end: 14 Playwright tests (no change). CI: the `tests` and
  `container` jobs both pass, about 2 minutes a run; the container job is the test
  of the Dockerfile, checking 2,000 loans at `/api/health`, the SPA at `/` and a
  non-root user.
- My take:

## Step 1e, the LoanIQ Labs brand (2026-11-19)
- Built: the LoanIQ Labs logo in the header (the flask-and-brain horizontal logo for
  dark backgrounds, 48 px high, read out as "LoanIQ Labs"), the flask favicon in the
  browser tab, a web manifest with the 192 and 512 px app icons, and the tab title
  "LoanIQ · LoanIQ Labs". The brand colours are CSS tokens (`--brand-navy`,
  `--brand-gold` and the rest). The page keeps the design board's palette.
- Desk problem it solves: a visitor can see whose work this is at a glance, and can
  find the tab among a dozen others, while the screen's colours still mean only
  what they meant before (blue to act, amber to warn, red for late loans).
- My key decisions: `brand/` is the only copy of the artwork, published by the build
  and never copied into the app; Neural Gold stays inside the logo instead of
  becoming a UI accent, so it never competes with the amber synthetic-data warning;
  the web manifest lives with the app in `frontend/public/`.
- What Claude Code did: read the brand README and sheet; proposed the plan and three
  open decisions; wrote a small Vite plugin that serves `brand/icon/` at `/icon/` in
  dev and copies it into the build, an `@brand` alias for the header logo, the
  favicon links and manifest, the header change, the brand tokens, a WCAG contrast
  checker, the tests and the decision record; took a screenshot of the header; ran
  every layer. Along the way: Vitest's `css: false` setting turns even a raw CSS
  import into an empty string, so the contrast test reads `styles.css` from disk;
  jsdom's `URL` class rejects `file:` URLs, so test paths are built with `node:path`;
  FastAPI answers unknown paths with the app's page (status 200), so the icon test
  checks for an image type, not just 200. Existing title tests now find the logo by
  its accessible name, and also check that the image really loaded and is 48 px high,
  its natural size.
- What I changed after review: the logo from 28 px to 36 px high, after the screenshot
  showed "LoanIQ" smaller than the tagline and "LABS" barely legible. "LABS" was still
  hard to read at 36 px, so I had the header logo redrawn for 48 px in Claude Design
  (a bold "LABS" with a gold rule, Space Grotesk lettering) and added it to brand/
  as loaniq-labs_horizontal_dark-bg_48px.svg.
- Tests and coverage: every layer passes through `test.ps1`. Back end: 184 tests (no
  change), coverage 98.8%. Front end: 104 Vitest tests (22 new: the icon plugin's
  build and dev-server hooks, including "../" paths; WCAG AA contrast for every text
  colour on its background; the brand tokens against `brand/README.txt`; the logo in
  the heading). End to end: 14 Playwright tests (1 new, for the favicon, app icons and
  manifest; 2 updated, for the logo and the tab title) against the built app.
- My take:

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
