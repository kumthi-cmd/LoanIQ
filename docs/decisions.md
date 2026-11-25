# Decisions
One entry per design decision, newest first.

## 2026-11-25: Product Slotting is a sidebar action and a dialog over any screen
Decision (Step 5b): the sidebar's planned "5 Slotting" link is now a **Product
Slotting** button (`nav.ts` `action: "product-slotting"`, drawn by
`components/SlottingNavButton.tsx`) that opens the run dialog
(`components/SlottingDialog.tsx`) from any screen, as on the "5 · Product Slotting"
board. Its state lives in one React context in the app layout
(`slotting/SlottingContext.tsx`), shared by the sidebar, the dialog and the Loan Tape. A
run started elsewhere ends on the Loan Tape. The confirm dialog's tape line shows loans
and fields from `/api/tape`; the board's "as of 2026-11-01 · seed 42" is left out, since
the API does not know either. The rules line comes from a rules summary added to
`GET /api/slotting/status`.
Why: slotting is something the desk does to the tape, not a place it goes, and one
context means the "Last run" line, the panel and the grid can never disagree.
Alternative considered: a slotting screen (rejected in Step 4e), or having the
generator write the as-of date and seed beside the tape (extra scope for one line).

## 2026-11-25: The Slotting panel replaces the note-rate distribution
Decision (Step 5b): the Loan Tape's middle panel is now Slotting: loans per spec-story
family, generic TBA and not slotted, from the last run's totals, or a "Run Product
Slotting" button before any run. The Note rate distribution panel is no longer drawn.
`components/NoteRatePanel.tsx` and its unit tests are kept (the API still sends the
buckets), so the panel can come back elsewhere, for example in Step 6.
Why: the board puts Slotting in that place, and three panels keep the 1440 px layout of
Step 1g. Once a tape is slotted, its coupons are in the Slot column.
Alternative considered: four panels in a row (narrower bars, and the one-line titles of
Step 1g would wrap).

## 2026-11-25: Slot and Spec Stories show by default once a run exists
Decision (Step 5b): `api.toml` `[columns] default_visible` lists `slot` and
`spec_stories`; they appear only after a run, so an unslotted tape is unchanged, and
Ask the Tape (the seller's tape only) never gets them. At 1440 px the tape's 12 default
columns still fit; the two new ones scroll sideways (`SLOT_COLUMN_WIDTHS`). The screen
paces the commentary at 350 ms a line and holds the totals 1.5 s
(`slotting/slottingConfig.ts`, illustrative), or shows every line at once for
reduced motion. In Playwright, the Product Slotting spec is its own project that runs
after all the others, because a run changes the one shared server for every test
after it.
Why: the board shows both columns after a run; a run is what the visitor asked for.
Alternative considered: keeping them hidden until chosen in Columns (a visitor would
not find what the run just did).

## 2026-11-25: Slotting eligibility: three checks, first failure is the reason
Decision (Step 5a): a loan is slotted when its program has an agency pool (Conventional
and High-Balance to UMBS; FHA, VA and USDA to GNMA II; Jumbo and Non-QM to none), its
product is a 30-, 20- or 15-year fixed (the TBA products), and it is current. The checks
run in that order and the first one a loan fails is its reason, so each not-slotted loan
is counted once (312 no agency pool, 85 ARMs, 136 delinquent on the seeded tape). Rules
in `backend/app/config/slotting.toml`; every program the generator knows must be in
exactly one agency list, or the app does not start.
Known simplification: modified loans (29), loans in forbearance (6) and high-LTV
refinances (17) on the seeded tape are slotted when current. A real desk would treat
them separately; kept so the rules stay three plain checks and match the design board.
Why: three checks a desk recognises, a single reason per loan, and totals that add up.
Alternative considered: the earlier Step 5a design (whole-loan execution, not-deliverable
reasons for modified and forbearance loans, per-product rules), replaced before merge by
this simpler set.

## 2026-11-25: The coupon rule: one minimum strip, round down, one step up
Decision (Step 5a): down coupon = note rate minus the minimum strip (0.50, illustrative),
rounded down to the coupon step (0.5); up coupon = down + one step. Both in
`[coupons]` of `slotting.toml`. The SQL works in whole units of 0.0001% with integer
rounding, so the answer is exact.
Why: one rule for both agencies, easy to follow on screen, and two coupons per loan are
what Best Execution needs to compare. Rounding down always leaves at least the minimum
strip for servicing and the guarantee fee.
Alternative considered: per-agency fees with maximum spreads and buy-downs (the earlier
design): closer to the agencies' guides, but harder to explain and not needed until
pricing.

## 2026-11-25: One shared slotting result, in memory, one run at a time
Decision (Step 5a): slotting runs on the whole tape when a visitor asks
(`POST /api/slotting/run`), and the result is shared by every visitor: same tape, same
rules, same answer. A `threading.Lock` lets one run go at a time (HTTP 409 for a
second). The result lives in memory like the tape, in a `slots` table and a
`loans_slotted` view the Loan Tape switches to; after a restart
`GET /api/slotting/status` says not run. A run publishes in one transaction at its last
step, so a run stopped early leaves the last result as it was. This changes one part of
the Step 4e decision below: slotting covers the whole tape, not only the loans the
trader has filtered or selected (the grid can still filter on the new columns).
Ask the Tape keeps reading the seller's tape only (a follow-up).
Why: a per-visitor result would mean storing one copy of the slots per visitor for no
new answer, and a lock is the simplest way to keep two runs from overwriting each other.
Alternative considered: slotting as the tape loads (the earlier design; no run for the
visitor to watch) or per-visitor results (more memory, same numbers).

## 2026-11-25: The server runs at full speed; the screen paces the commentary
Decision (Step 5a): the run streams one server-sent event per step (13 on today's
config: load, rules, three checks, eligible, coupons, one per story family, overlaps,
write) with the step's name, percent and a commentary line filled with real counts,
then a done event with the totals. The server never sleeps between steps; on 2,000
loans a run takes about a tenth of a second, and 50,000 loans must finish within
`slotting_run_budget_ms` (`api.toml`). Step 5b's screen spaces the lines out so a
visitor can read them. Words, with placeholders, live in `content/slotting.json`.
Why: honest timing (the commentary shows what the engine did, not a staged delay),
fast tests, and pacing is a display choice that belongs to the screen.
Alternative considered: sleeps on the server to make the run look busy (slower tests,
and the counts would arrive late for no reason).

## 2026-11-25: Slotting and best execution are Loan Tape features, not screens
Decision (Step 4e): product slotting and best execution run on the Loan Tape, on the
loans the trader has filtered or selected, instead of on screens of their own. Step 5
turns the planned "Slotting" sidebar item into a "Product Slotting" action on the Loan
Tape. `frontend/src/nav.ts` is unchanged until then. Ask the Tape gets no "Send to
Slotting" button (the 4b plan hid it until Step 5): "Open in Loan Tape" already takes an
answer's loans there. The build order is now Steps 5 and 6, then 2 and 3, then 7, 8
and 9.
Why: a desk slots and prices the loans it is already looking at. A separate screen
would mean sending the same loans somewhere else first, and the Loan Tape already holds
the filters, the selection and the pool summary.
Alternative considered: separate Slotting and Best Execution screens fed by "Send N
loans to Slotting" (an extra hand-off, and a second grid of the same loans).
Superseded in part (2026-11-25, Step 5a): slotting runs on the whole tape as one shared
result, not only on the loans the trader has filtered or selected; see "One shared
slotting result, in memory, one run at a time" above. The rest of this decision stands.

## 2026-11-24: The Agent mark is a button beside the link, never inside it
Decision (Step 4d): screens answered by an AI agent (`agent: true` in
`frontend/src/nav.ts`, Ask the Tape only for now) carry a small gold "Agent" mark: the
LoanIQ Labs flask and the word "Agent". In the sidebar it is its own button right
after the link, in the same row, and the link is named "Ask the Tape, agent". It also
sits beside the Ask the Tape title. Hover or focus shows the glossary's "Agent"
definition in one line. A click opens a popover with `content/agent.md` and the loop
diagram `content/diagrams/ask-the-tape-agent.svg`, shown as an `<img>`.
Why: a button inside a link is invalid HTML, and a click on it would also navigate.
An `<img>` keeps the SVG's markup out of the page. The popover is drawn at the end of
the page with fixed position, so the scrolling sidebar cannot clip it.
Alternative considered: a badge inside the link (invalid, and it navigates), or a
separate About-the-agent page (takes the visitor away from the screen).

## 2026-11-24: Planned Tape Upload and Explorer move to the end of Trade
Decision (Step 4d): Tape Upload (Step 2) and Explorer (Step 3) now sit after
Optimizer, at the end of the Trade group. They keep their step numbers and "Planned"
tags. The Tape group holds only the live Loan Tape and Ask the Tape.
Why: both are later development (Step 4 was built ahead of them), so the screens a
visitor can use come first.

## 2026-11-24: One default-column list for both screens, added to loan-level answers
Decision (Step 4c): the 12 columns a trader reads first (loan ID, seller, program,
product, state, note rate, current UPB, FICO, LTV, DTI, DQ status, occupancy) live
once, in `backend/app/config/api.toml` `[columns] default_visible`. Before, they were
in the front end's `gridConfig.ts`. `GET /api/loans/columns` marks each column
`default_visible`, and the Loan Tape opens with those columns showing. The same list
is used for Ask the Tape: when a `query_tape` result has one row per loan (a
`loan_id` column, no ID repeated, unique column names), the server fetches the
missing default columns for those loan IDs with one parameterised query and joins
them on. Columns run loan ID first, then the defaults in tape order (as the Loan Tape
grid shows them), then the agent's other columns. Rows keep the agent's order.
The model still reads only the columns its SQL selected. The stored SQL and the
"Open in Loan Tape" link are the agent's own query. `added_columns` on the stored
result says which columns were joined on. Grouped results are left as written.
The result table is packed to its data (CSS `width: auto`, tighter padding, headers
that may wrap).
Why: an answer about specific loans often came back as two or three columns
stretched across the panel. A trader wants the same fields beside every loan, in the
same order as the Loan Tape. Keeping the list in one place stops the two screens
drifting apart. Hiding the added columns from the model keeps its token cost and its
answers unchanged.
Alternatives considered: telling the model in its prompt to select these columns
(not guaranteed, and it costs tokens); a list of 10 that left out DQ status and
occupancy (rejected so both screens match); having the front end fetch the extra
columns (one more request per table, and saved-query reruns would need it too).
Illustrative display choice, not an industry rule.

## 2026-11-24: "Open in Loan Tape" turns the answer's WHERE into the grid's own filters
Decision (Step 4b): the back end reads each `query_tape` result's WHERE and ORDER BY
with sqlglot (`backend/app/agent/loan_tape_link.py`) and writes them as AG Grid's
filter model and the grid's sort string. The Loan Tape reads them from its URL
(`/?filter=…&sort=…`). Only an AND of simple conditions translates: `=`, `<>`, `>`,
`>=`, `<`, `<=`, `BETWEEN`, `IN` with up to two values, `LIKE '%text%'`, with at most
two conditions per column (AG Grid's limit). Anything else (OR across columns, a
longer list, a function, HAVING, a subquery, a date column) gets a reason instead,
and the button is disabled with that reason. To fit what agents write, the grid's
number filter gains "greater/less than or equal" and "not equal", in
`loan_query.py` and `loanColumns.ts` alike. LIMIT is ignored: the grid shows every
matching loan.
Why: the trader sees the answer's filter as ordinary column filters they can read
and change, and the link stays short enough to bookmark or send. A test checks that
for every translatable query the grid's API counts exactly the loans DuckDB finds
with the agent's own WHERE. The link is data, never SQL; `/api/loans` checks it like
any filter a trader types.
Known differences: the grid's text "equals" and "contains" ignore case, while SQL's
`=` and `LIKE` do not. The tape's codes are upper case, so the counts agree on this
tape.
Alternatives considered: a list of loan IDs (works for every query, but isn't "the
same filter" and breaks past a few hundred loans); the query id (expires after an
hour, and the grid would need a second, hidden filter path).

## 2026-11-24: Saved queries live in the browser and rerun through the agent's own gate
Decision (Step 4b): "Save query" keeps an answer's SQL (as the screen showed it)
with a short tag in the visitor's localStorage, the last five. Clicking one sends
the SQL to `POST /api/ask/rerun`. That route runs it through `TapeTools.run_query`,
the same `sql_guard` check, row cap, timeout and read-only tape as the model's
`query_tape`, and never calls a model.
Why: a per-visitor convenience needs no server state and no accounts. Rerunning
costs nothing and follows the same rule each time. The route accepts SQL from the
browser, but only what the agent itself may run, so it opens no new kind of access
to the synthetic tape. Storage is wrapped in try/catch, so a blocked or full
localStorage just means saved queries don't survive a reload.
Alternatives considered: saving on the server (needs visitor identity and cleanup);
rerunning the question through the model (costs money and may write different SQL).

## 2026-11-24: Ask the Tape answers show plain tables; the header and Ctrl K fill, never send
Decision (Step 4b): every result shows as a table formatted like the Loan Tape. The
first 8 rows show, as on the design board, with "Show all" for the rest. The
board's bar chart for "90+ by seller" is not drawn per answer type yet. Loan IDs
open a drawer through the agent's `get_loan` tool (`GET /api/ask/loans/{id}`). The
header's "Ask the tape" box and Ctrl K open `/ask?q=…` with the question filled in
but not sent. "Send to Slotting" is hidden until Step 5. A small Offline banner
shows while built-in rules answer for a lasting reason (no key, daily budget,
visitor limit), from a new `GET /api/ask/status`. A one-off fallback, such as a
timeout, stays a notice under that answer.
Why: one table component covers every answer shape and keeps numbers exact.
Filling without sending means a stray Ctrl K never spends a model call. A banner
before the first question sets expectations.
Alternatives considered: a chart chosen per answer shape (later, if answers need
it); sending the header question at once (faster, but spends money on half-typed
questions).

## 2026-11-24: A failed model call logs the provider's own message, never the key or question
Decision (Step 4b): adapters wrap SDK errors with `sdk_error`, which keeps the HTTP
status and the provider's own error message: Anthropic's `error.message`, OpenAI's
`message`, else the exception text. The message is cut to 300 characters and
anything shaped like a key is redacted: `sk-…`, `AIza…`, `x-api-key`, `Bearer`, and
the value of every `*_API_KEY` variable. The orchestrator logs one warning line,
`provider_error`, with provider, model, reason, status and message. If the provider
echoed the visitor's question back, it is replaced with `[question]`. The
Playwright server now starts with `ANTHROPIC_API_KEY` blank, so e2e runs on the
built-in rules whatever key is set in the shell.
Why: Render's logs said only `http_400`; the operator needs "credit balance too
low" or "model not found" to fix it. Keys and visitors' questions stay out of logs.

## 2026-11-23: Ask the Tape runs LoanIQ's own loop behind one provider interface
Decision (Step 4a): the agent loop is LoanIQ code (`backend/app/agent/orchestrator.py`)
calling the Messages API one round at a time, not Anthropic's Managed Agents or the
SDK's tool runner. Every vendor sits behind `LLMProvider.chat()` (Strategy pattern):
Anthropic (live), Offline (built-in rules), Fake (tests), OpenAI and Gemini (off
until a key is set). Tools are defined once as JSON Schema; each adapter translates
them and handles its own prompt caching (an explicit mark for Claude, automatic for
the other two). All three SDKs are pinned in `requirements.txt` and imported only
when their provider is used.
Why: LoanIQ must see and check every tool call, count refusals, switch model
mid-question and stop on its own 20-second clock; and the same loop must drive
every vendor and the offline rules, so the screen and the tests see one engine.
The tools read a local DuckDB file, so there is nothing for a hosted sandbox to do.
Pinning all three SDKs means the OpenAI and Gemini adapters are tested against
those SDKs' real response types, not hand-made look-alikes.
Alternatives considered: Managed Agents (Anthropic hosts the loop and a sandbox;
more than this needs, and it would not drive other vendors); the SDK tool runner
(less code, but no place to count refusals or switch model mid-loop); pinning only
`anthropic` (smaller image, but untested adapter code).

## 2026-11-23: Ask the Tape queries pass three layers: allowlist, row cap, read-only file
Decision (Step 4a): `query_tape` SQL is checked by sqlglot against an ALLOWLIST of
syntax-tree nodes and functions, the table `loans` and the tape's columns
(`backend/app/agent/sql_guard.py`). Filter values are lifted out into named bound
parameters (`$p1`, `$p2`). The LIMIT is capped at 500 + 1 rows and each query is
interrupted after 2 s. The query runs on a copy of the tape in a DuckDB file opened
`read_only`, with external file access off and settings locked
(`backend/app/agent/tape_db.py`). Limits live in `backend/app/config/llm.toml`.
Why: the model's SQL is untrusted text. An allowlist refuses anything it does not
know, including file readers such as `read_csv`. Named parameters, not `?`: tests
showed sqlglot's tree walk does not follow print order, so positional values could
bind to the wrong column. DuckDB cannot open an in-memory database read-only, so
the copy is a small file in a new temporary folder on every start. Even a query
that got past the checks could then not write or read anything but the tape.
Alternatives considered: a denylist of dangerous keywords (fails open on a new
trick); asking the model to send values separately (more for a small model to get
wrong); running on the grid's in-memory connection (writable).

## 2026-11-23: Claude Haiku 5.5 answers, Sonnet 5.5 after two refusals, rules as fallback
Decision (Step 4a): tape questions run on `claude-haiku-5-5` at effort "low", with
800 output tokens per call, at most 5 rounds and 20 seconds. After 2 refused tool
calls in one question, the rest runs on `claude-sonnet-5-5`. Built-in rules answer
when there is no key, when the model fails, times out, declines or runs out of
rounds, when today's budget is spent, and always for desk-question chips. The answer
says which. Prices in `llm.toml` are illustrative, from Anthropic's price list on
2026-11-23.
Why: the model only plans and explains; the tools do the math, so the cheapest
current model at low effort is enough, and a stronger one is paid for only when the
small one keeps writing bad queries. A visitor always gets an answer from the tape.
Alternatives considered: Sonnet for everything (about 20 times the price for the
same plan-and-explain job); no fallback (a dead screen whenever the API is down);
Anthropic's server-side refusal fallback (LoanIQ's own fallback covers refusals and
every other failure the same way).

## 2026-11-23: Ask the Tape budget is counted in memory; visitors by hashed address
Decision (Step 4a): every question's tokens are priced in Decimal dollars and logged
as one JSON line (no question text, no address). A daily cap ($2.00) and a
per-visitor limit (30 questions per UTC day) live in `llm.toml`, counted in memory
(`backend/app/agent/budget.py`). A visitor is a salted hash of the last
`X-Forwarded-For` entry, the one Render's proxy adds.
Why: enough to stop runaway spend on a showcase with no database. The counts reset
when the server restarts (Render's free plan sleeps after 15 idle minutes), so the
cap is a guard, not a ledger; set a monthly spend limit in the Anthropic Console as
the hard backstop. Earlier `X-Forwarded-For` entries can be typed by anyone, so they
are ignored.
Alternatives considered: a database or Redis for exact counts (a new service for a
showcase); no per-visitor limit (one visitor could spend the whole day's budget).

## 2026-11-23: POST /api/ask streams events with FastAPI's built-in SSE
Decision (Step 4a): `POST /api/ask` answers with Server-Sent Events (FastAPI 0.165's
`EventSourceResponse`): `tool_call`, `tool_result` (with the SQL and a query id),
`escalated`, `fallback`, `answer`, `done` (tokens, cost, models). Each step streams
as it happens; the answer arrives whole, not word by word. Full results are kept by
query id in memory for an hour (`GET /api/ask/queries/{id}`); the model sees totals
and 20 rows as CSV.
Why: the visitor watches the agent work, and the SQL behind every number is on
screen. Streaming the text word by word would mean a streaming path in all five
adapters for little gain on a two-to-four-sentence answer; it can come later.
Alternatives considered: one JSON response at the end (the screen is blank for
several seconds); WebSockets (two-way, more than needed).

## 2026-11-23: Golden questions are graded against the tape, not against stored answers
Decision (Step 4a): `backend/evals/golden_questions.toml` holds 21 questions. Each
has a `truth_sql` that computes its true answer from the loaded tape, and a
reference query the Fake runs in CI through the real guardrails and tools. The
grader (`backend/app/agent/golden.py`) accepts a number when it is the true value
correctly rounded to the precision the answer wrote (within half a step) and within
5% of it. `backend/scripts/eval_agent.py` runs the same questions on live models.
Why: answers follow the tape when the generator changes, so the file never goes
stale. The rounding rule matches how a trader writes numbers ($3.5M, 6.41%) without
letting a wrong one through: a first, looser rule let 6.5% pass for 6.41%, and a
test caught it.
Alternatives considered: hard-coded answers (stale on the next tape change); an LLM
judge (costs money on every CI run, and is less predictable than a number check).

## 2026-11-23: Loan Tape at 1440 px: explanation closed by default, columns fitted to content
Decision (Step 1g, closing the Step 1d layout follow-ups, checked against the
"1 · Loan Tape" board at 1440 px and measured in Chromium):
- The "Explain this screen" panel starts closed; one click opens it. This replaces
  "the explanation open beside the grid" in the 2026-11-19 entry below.
- The 12 default columns start at widths fitted to their content
  (`DEFAULT_COLUMN_WIDTHS` in `frontend/src/grid/gridConfig.ts`, 1,135 px in all),
  not AG Grid's 130 px each. At 1440 px all 12 show with the explanation closed;
  with it open, the first 8 show and the grid scrolls sideways for the rest.
- The "Desk questions" label sits on its own line above the chips, so all six chips
  fit on one row at 1440 px, open or closed.
- The note-rate panel caption is the board's "UPB by 0.5% bucket" (the width read
  from the data), and panel titles never wrap.
- Axis labels: the first at the left edge, middle ticks centred on their bucket's
  edge, the open-ended last one written short ("9%+", as on the board) and
  right-aligned at the axis end.
Why: the board's own table needs about 1,100 px for 12 columns, more than the grid
has beside a 300 px explanation at 1440 px, so no width setting fits all 12 with
the panel open. Closing it by default gives a trader the whole default tape at
once, and the explanation is still one click away on every screen. The chip label
and the short caption keep the board's chip and title sizes instead of shrinking
them.
Alternatives considered: a narrower explanation panel (changes the board); smaller
chips or a 200 px sidebar like the board (only just fits, and "Blotter & Positions
Planned" gets tight); keeping the explanation open and accepting about 9 columns.

## 2026-11-23: The flask holds a house and a coin, not a brain
Decision: the LoanIQ Labs symbol keeps the v1 flask, but the brain is replaced by a
house standing in blue liquid with a gold $ coin on its front, drawn as a flat,
chunky icon. Redrawn so far: the 48 px header logo, the stacked logo on the About
page and every file in brand/icon/. File names are unchanged, so no code or tests
change. The 16 and 32 px icons use a simpler flask (no bubbles, plain coin).
Why: the house and coin point to home loans; the flask keeps the "Labs" idea and
stays close to the old symbol.
Alternatives considered (Claude Design canvas, 2026-11-23): a hand presenting a
beaker, a beaker shaped like a house, and a coin dropping into a beaker. A draft with
a hand under the house was dropped because the hand did not read as a hand.
Note: the light-background, mono and PNG logos in brand/logo/ and brand-sheet.png
still show the v1 flask and brain. The new files in brand/icon/ carry C2PA content
credentials (provenance records), added when they were delivered; the 48 px header
file's old credential was removed, because it described the old artwork.

## 2026-11-23: Build facts written by test.ps1 and committed, not written in CI
Decision: after all five layers pass, a plain function at the end of `test.ps1`
(`Write-BuildFacts`) writes `content/build-facts.json`: back-end, front-end and
end-to-end test counts, back-end coverage, the commit count and the date. The file is
committed; the How it was built page shows it under "By the numbers", and the Docker
build bundles the committed copy.
- Not a sixth `Invoke-Step`, and the five layer commands are unchanged, so `ci.yml`
  and `test.ps1` still run the same layers (`test_deploy_config.py`).
- Nothing is re-run. Back-end and end-to-end counts come from `pytest --collect-only`
  and `playwright test --list`; coverage from the `.coverage` file pytest-cov leaves.
- The front-end count comes from a JSON report the Vitest layer now writes
  (`frontend/test-results/vitest.json`, set in `vite.config.ts`), not from
  `vitest list`, which counts an `it.each` table as one test (91 against 104 run).
- Every number is optional on the page: a missing one shows as a dash.
- About and How it was built have no Explain panel: each page is itself the explanation.
Why: the hosted site needs numbers, but CI writing to the repo would need write
permission and a bot commit on every push. Committing a file from a green local run
keeps CI read-only.
Trade-offs: the commit count is taken before the run's own commit, so it is one
behind; the file changes on most test runs, so it often shows in `git status`.
Alternative considered: CI writes the file into the image at build time. Rejected for
now: the container job would need the test results from the tests job.

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
- DigitalOcean App Platform: runs the same container with similar ease. Not
  chosen because Render's free plan lets us start at no cost while the site is being
  built; worth comparing prices again before upgrading.
- Google Cloud Run: scales to zero and has a free allowance, but needs a Google Cloud
  project, billing, a container registry and access settings before the first deploy.
  A good next home if traffic grows, with no change to the Dockerfile.
- AWS Lightsail containers: runs the same container, with fixed monthly pricing.
  Not chosen because it needs an AWS account and more setup than Render's Blueprint,
  for a site that does not need AWS yet.
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
