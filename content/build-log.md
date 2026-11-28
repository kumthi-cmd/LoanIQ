# Build log
One entry per step, newest first. Copy the template for each new step.

## Step 6c, the Price Grid screen (2026-11-28)
- Built: the Price Grid at `/prices`, the desk's price file on screen
  (`frontend/src/screens/PriceGridScreen.tsx`, `components/pricing/`).
  - A strip with the trade date, the Treasury curve's date and whether it is live,
    cached or the sample, the source, and links to Treasury and SIFMA.
  - Six product cards: current coupon and where it comes from (10Y 4.940 + 1.350 =
    6.290% on UMBS 30), SIFMA class, Current month, notification and settlement
    dates, days to the next settlement, financing rate.
  - The TBA price table: a price and a drop in 32nds per product at each coupon,
    the coupon nearest each current coupon tinted, model-only coupons muted, and the
    decimal on hover.
  - The spec pay-up table for one product at a time, showing the S-curve from 0 on
    discounts to the full pay-up on premiums ("18+" = 18.5/32).
  - One "Traded coupons / All 25" switch for both tables; the Explain panel with 13
    new glossary terms.
- Desk problem it solves: a trader sees today's prices, drops and pay-ups for every
  product in one place, with where each number comes from, before best execution
  uses them.
- My key decisions:
  - Option 2 of two: Claude drew the design on a Claude Design canvas from the plan,
    with live numbers, and I reviewed it before any code ("Looks good").
  - Plain tables, traded coupons by default, colour for meaning only (no red on a
    negative drop), financing rate as a 13th glossary term, CPR and SMM in the
    glossary rather than as columns.
- What Claude Code did:
  - Drafted the 6c prompt, then the plan, then the "6 · Price Grid" canvas: the Loan
    Tape's colours and fonts, today's live grid, with working switches, chips and
    Explain panel.
  - Built the screen, the view helpers and a small hand-written price file for the
    tests; wrote the explanation and the glossary entries.
  - Added `components/GlossaryCaption.tsx`, so captions in `content/` can mark a term
    as `[[Drop|drop]]` and still explain it on hover, instead of hard-coding the term
    in a component. A first version split the caption text around fixed words; it was
    replaced before review as too fragile.
  - Followed the frontend rule over the design for rates (6.290%, not 6.29%), and
    recorded the difference in the roadmap.
  - Caught by a test: the new check that every marked term has a glossary entry
    failed on "Term", the example in the content file's own note. The check now skips
    that note, which is never shown.
- What I changed after review:
  - Caught on the screenshots: at six cards across, "Notify 08 Dec · Settle 10 Dec"
    left "Dec" alone on a line. The two halves now never break inside, so the line
    wraps at the dot.
- Tests and coverage: every layer passes through `test.ps1`.
  - Back end: 709 tests, unchanged (no back-end change), coverage 99.1%.
  - Front end: 278 tests (53 new).
    - `pricing/priceGridView.test.ts`: traded coupons from `model_only`, the nearest
      coupon (and its tie rule), table rows matched by coupon, pay-ups as "18+", dates
      without a time-zone shift, rates to three decimals.
    - `PriceTable`, `PayupTable` and `ProductCard` tests: the price and drop pairs, the
      decimal on hover, the nearest tint said out loud, muted model-only cells, a
      negative drop, the S-curve across a pay-up row, the product chips, the curve's
      freshness badge and the source links.
    - `PriceGridScreen.test.tsx`: the whole screen on the real routes, one switch
      for both tables, the 503 message, and the Explain panel with its 13 terms.
    - `GlossaryCaption.test.tsx`, plus a content check that every marked term exists.
    - `App.test.tsx` and `routes.test.tsx`: the sidebar and live routes now include
      the Price Grid (expected lists extended; nothing removed).
  - End to end: 35 tests (3 new in `price-grid.spec.ts`): open from the sidebar, six
    cards and a price in 32nds with its decimal; all 25 coupons in both tables and
    another product's pay-ups; the Explain panel's tabs.
- My take:

## Step 6b, the SIFMA calendar and the rolling Current month (2026-11-27)
- Built: the price file's Current column now means a real delivery month, and every
  coupon carries its drop (`backend/app/pricing/settlement.py`, `model.py`).
  - SIFMA's notification and settlement dates by class, November 2026 to December
    2027, in `pricing.toml` `[settlement]`: Class A 30-year UMBS, Class B 15-year
    UMBS and Ginnie Mae (and the 20-years), Class C 30-year Ginnie Mae.
  - Current is the first month whose 48-hour notification date is today or later, in
    New York: it rolls the day after notification. On 2026-12-09 UMBS 30 quotes
    January while the others still quote December.
  - The drop, Current minus the next month, in 32nds: one month of coupon, minus
    financing at the 1-month bill yield over the days between SIFMA settlement
    dates, plus prepaid principal back at par (CPR 6% to 25% on the pay-up S-curve).
    UMBS 30 6.0 on Thanksgiving: 0-03+. Low 15-year coupons go negative.
  - The API's Current column gives the month, class, dates, days and financing rate,
    and each cell its drop ("0-03+", "-0-01"). Past SIFMA's last month it answers
    503 rather than guess.
- Desk problem it solves: a TBA price is for a delivery month, and the desk needs to
  know which month "Current" is today and what rolling into the next one is worth.
  Both now follow SIFMA's published dates.
- My key decisions:
  - Scope 6b to the back end: the calendar and the rolling Current month, with the
    screen in 6c and best execution in 6d.
  - One Current column plus the drop, not three month columns.
  - Roll the day after the 48-hour notification date, not after settlement.
  - Add SIFMA's calendar as a source; settle 20-year pools with Class B.
  - CPR 6% to 25% and a 0 financing spread to start.
- What Claude Code did:
  - Drafted the 6b brief, then a narrower one when I asked whether 6b was only the
    calendar, and explained what one Current column means.
  - Read SIFMA's page and spreadsheet: the dates and the KEY of classes, and found
    that 20-year pools are not in it.
  - Copied the dates from the spreadsheet's own date values, spot-checked against the
    page, into `pricing.toml`.
  - Wrote the calendar module, the drop and the signed 32nds, and the new API fields;
    added SIFMA to the API's sources.
  - Design choice for review: the drop's prepayment speed reuses the pay-up S-curve,
    so one shape describes the refinancing incentive.
  - Caught by a test: the timing test failed at about 120 ms per price file (budget
    50 ms). Profiling found the 1/12 power in SMM and the rounding target worked out
    for every cell; both are now computed once and cached, and the pay-up S-curve is
    shared across stories. About 20 ms now, budget unchanged.
- What I changed after review:
- Tests and coverage: every layer passes through `test.ps1`.
  - Back end: 709 tests (43 new), coverage 99.1%. No test touches the network.
    - `test_pricing_settlement.py`: SIFMA's class for each product, December 2026's
      published dates, the roll the day after notification, classes rolling on
      different days, the year-end roll, a 503 past the end of the calendar, a check
      that fails about three months before the dates run out, and bad calendar config.
    - `test_pricing_drop.py`: the worked example (UMBS 30 6.0 = 0-03+), SMM and CPR,
      financing and the spread, a negative drop, prepayment helping discounts and
      hurting premiums, 28 against 35 days, signed 32nds, and bad drop settings.
    - `test_pricing_model.py` and `test_pricing_api.py`: updated for the trade date,
      the drop fields and the roll fields. The price file still builds in about
      20 ms (the 50 ms budget is unchanged).
  - Front end: 225 tests, unchanged (no new screen in this step).
  - End to end: 32 tests, unchanged.
- My take:

## Step 6a, the price file (back end) (2026-11-27)
- Built: an illustrative price file at `GET /api/prices/grid`, from free public data
  (`backend/app/pricing/`, settings in `backend/app/config/pricing.toml`).
  - The daily anchor is Treasury's Daily Par Yield Curve XML feed, fetched on the
    first request of each New York day and kept in memory. It uses the latest curve on
    or before today (on Thanksgiving, Wednesday's), and last month's on the 1st.
  - If Treasury can't be reached it keeps the last curve; with none, it uses a
    recorded month (November 2026), and the label says so.
  - Six rows (UMBS and GNMA II, 30, 20 and 15 years), one "Current" month column, 25
    coupons from 1.0 to 13.0 on slotting's 0.5 step.
  - Current coupon = the anchor Treasury yield + a spread. The price is 100 at the
    current coupon, falls by duration x the gap below it, and flattens above it (the
    prepayment cap). Exact Decimal, shown in 32nds ("101-23+"); coupons outside each
    product's traded band are flagged `model_only`.
  - Spec pay-ups: `payup_32nds` per story and per LLB tier in `spec_stories.toml`,
    scaled by an S-curve from 0 at discount coupons to the full pay-up at premium
    coupons.
  - A `PriceSource` strategy like the LLM provider layer: the model now, a desk's own
    file and a vendor feed as stubs that answer "not configured".
- Desk problem it solves: a desk can't run best execution without a price file, and
  LoanIQ has no paid feed. This gives one that moves with the market every day, says
  plainly that it is illustrative and as of when, and can be swapped for real prices
  without changing best execution.
- My key decisions:
  - Price from a model anchored to Treasury's free daily curve, with no Freddie Mac
    sources (FRED's mortgage rate included) and FINRA's TRACE TBA tables only as a
    manual shape check (free for non-commercial use only).
  - Six products, one Current month for now (6b adds the rolling calendar), coupons
    1.0 to 13.0 on slotting's step.
  - Pay-ups per story and per LLB tier, scaled by an S-curve.
  - The PriceSource strategy, with file and vendor stubs.
  - Rebuild the file from the curve plus config, so Render needs no disk.
- What Claude Code did:
  - Planned the package, the formulas and the fallbacks; recorded Treasury's
    November 2026 month, which doubles as the bundled curve and the test fixture.
  - Wrote the Treasury parser and once-a-day cache (New York day, retry wait after a
    failure, DOCTYPE and size checks on the XML), the price model, 32nds formatting,
    the sources and the route, and pinned `tzdata` so the New York time zone works
    on Windows and in the container.
  - Added `payup_32nds` to the spec-story loader, with checks: one per tier, never
    rising as the cap rises.
  - Could not read the two Fannie Mae LLB papers (HTTP 403), so the pay-up sizes are
    illustrative and listed under "Rules without a recorded source".
  - Changed an existing test's setup: `test_new_tier_is_one_number` now adds the new
    tier's pay-up along with its cap, since each tier needs one; its assertions are
    unchanged.
- What I changed after review:
- Tests and coverage: every layer passes through `test.ps1`.
  - Back end: 666 tests (111 new), coverage 99.0%. No test touches the network: a
    fake feed serves the recorded Treasury month.
    - `test_pricing_model.py` (67): par at the current coupon, prices rising with
      coupon and flattening above par, no kink at par, the floor, `model_only` band
      edges, 32nds both ways, pay-up 0 at a discount coupon and full at a premium,
      tighter LLB tiers paying more, build time under 50 ms, and bad settings
      stopping the app.
    - `test_pricing_treasury.py` (23): parsing, the latest curve on or before today,
      last month's curve on the 1st, once per New York day, the fallbacks when
      Treasury is down, the retry wait, and refused XML.
    - `test_pricing_api.py` (13): the route's shape and label, the labels when
      Treasury is down, the 503 stubs, and the OpenAPI spec.
    - `test_spec_stories.py` (8 new): pay-ups load as exact 32nds; bad tier pay-ups
      are refused.
  - Front end: 225 Vitest tests (unchanged; API types regenerated). End to end: 32
    Playwright tests.
- My take:

## Step 5c, Ask the Tape's scope grows with the desk (2026-11-25)
- Built: Ask the Tape now follows the desk's stages: tape (parsing), slotting, best
  execution, optimization, pooling, trading (`backend/app/agent/stages.py`).
  - It knows the tape from the start. After a Product Slotting run, its read-only copy
    is rebuilt in the background with flat slot columns: `deliverable`,
    `not_slotted_reason`, `agency`, `slot`, `down_coupon`, `up_coupon`, `spec_stories`,
    `llb_tier`, and one `story_<family>` column per spec story.
  - The new copy is swapped in under a lock, and a question already running finishes
    on the old one.
  - The system prompt gains a short Slotting section; before a run it carries a
    "not run yet" line instead.
  - A new tool, `explain_slot`, gives one loan's slot card, the same as the Loan
    Tape's hover.
  - Ask the Tape shows a "Knows: Tape ✓ · Slotting – · BestEx –" strip.
  - Seven golden questions, each asked at its stage: six on slots, and one checking
    that the agent says slotting hasn't run.
- Desk problem it solves: a trader can ask about slots in plain English once the desk
  has slotted the tape: how many loans are deliverable, the UPB in UMBS, the LLB 85K
  tier, the New York story, or why one loan is not deliverable. The answer comes from
  the same result as the Loan Tape, and never from slotting the desk hasn't run.
- My key decisions:
  - The agent's scope grows stage by stage, Parsing -> Slotting -> BestEx ->
    Optimization -> Pooling -> Trading, instead of slotting its copy at start-up.
  - Include the scope strip.
  - Keep results in memory for now, with a simple Postgres planned with the paid
    Render plan, before trading.
- What Claude Code did:
  - Planned flat columns so the one-table SQL guard stays as it is, then reworked the
    plan around stages when I asked for an agent that grows with the desk.
  - Answered where each stage's results are stored.
  - Wrote the stage registry and the prompt files, and the agent's copy holder with
    leases and background rebuilds.
  - Wrote the slot columns in `slotting.py`, and the shared slot card (moved into
    `app/slot_card.py`).
  - Wrote `explain_slot`, the stage-aware prompt and tool list, the status stages,
    the strip, and the stage-aware golden format and eval script.
  - Design choices made while building, for review:
    - Answers' default columns follow the grid (Slot and Spec Stories after a run).
    - "Open in Loan Tape" links use only the grid's columns, so `story_ny` gives a
      reason instead of a broken grid.
    - A stage tool called too early gets a plain "not yet", not counted as a
      guardrail failure.
    - The copy is built in memory and written once. The first version took 3.3 s on
      50,000 loans, over the 3 s budget; this one takes about 2.0 s.
  - Bugs caught by tests:
    - `run_golden` reused a variable and dropped every question after the first.
    - My own concurrency test queried one DuckDB connection from four threads; the
      tools give each query its own cursor, and the test now does too.
- What I changed after review:
- Tests and coverage: every layer passes through `test.ps1`.
  - Back end: 555 tests, coverage 99.0%. 18 in the new `test_agent_stages.py`:
    - the order and states;
    - the prompt at each stage, and that it names exactly the slot columns;
    - the copy before and after;
    - a query in flight during a swap, and four threads querying through five
      rebuilds with no error;
    - a failed rebuild keeping the agent working, and a column clash refused;
    - the guard still refusing joins, other tables and WITH;
    - `explain_slot`: offered only after a run, "not yet" before, the board's two
      loans, and bad and unknown IDs;
    - links using only the grid's columns;
    - the status stages, and labels for every column.
  - Also new: the golden questions on the Fake at both stages, and a 50,000-loan
    rebuild timing test.
  - Tests updated because their rule changed:
    - the tool list (adds `explain_slot`);
    - the status (adds stages);
    - two slotting tests (the agent now learns slotting after a run);
    - the golden count, now split by stage.
  - The 50,000-loan page timing now waits for the agent's rebuild, so it measures the
    grid alone.
  - Front end: 225 Vitest tests (3 new, for the strip).
  - End to end: 32 Playwright tests (2 new: the strip before a run, and slotting
    known after one).
  - Live eval on Claude Haiku 5.5 (`docs/evals/2026-11-25-5c.json`, the second of two
    runs): 27 of 28, $0.0079 in all, $0.00028 a question, 3.1 s on average, no
    fallbacks. All seven slot questions passed. The miss, `ltv_over_125` in both runs,
    was right but written in words ("Twenty loans"), which the grader cannot read; I
    added a prompt rule to write every number in digits instead of loosening the
    grader. The rerun with the rule (`docs/evals/2026-11-25-5c-digits.json`): 28 of 28,
    $0.0075 in all, $0.00027 a question, 3.0 s on average, no fallbacks.
- My take:

## Step 5b, Product Slotting on the Loan Tape (2026-11-25)
- Built: the "5 · Product Slotting" board in the app.
  - The sidebar's planned "Slotting" link is now a **Product Slotting** button. It
    shows "Not run on this tape" or "Last run 11:42 AM" and opens the run dialog from
    any screen.
  - The dialog confirms what will run, from the API: the tape's loans and fields, and
    "12 rules in 4 spec stories: LLB tiers $85K to $275K, NY, PR, Low FICO". It then
    shows the progress bar and the running commentary one line at a time, and ends on
    the totals. It closes by itself on the Loan Tape, where a notice says what changed.
  - The grid gains Slot and Spec Stories, shown by default, with stories as pills.
  - Hovering or focusing a loan ID opens its card: pool, down and up coupons, each
    story with its rule and why, and the generic TBA line; or why the loan is not
    slotted.
  - The Slotting panel replaces the note-rate distribution, and the Explain panel can
    switch to a new Product Slotting explanation.
- Desk problem it solves: a trader runs slotting where the loans already are, watches
  what each check found, then reads where any loan can go without leaving the tape.
  That is the view Best Execution (Step 6) will price.
- My key decisions:
  - Product Slotting is a sidebar action and a dialog, not a screen.
  - The Slotting panel replaces the note-rate panel, as on the board.
  - The dialog's tape line shows loans and fields; the board's as-of date and seed are
    left out, because the API does not know them.
  - Slot and Spec Stories are visible by default after a run, even though they scroll
    sideways at 1440 px.
  - The Step 4e decision is kept, marked as superseded in part.
- What Claude Code did:
  - Planned the flow from the board and asked the three questions above.
  - Wrote a status rules summary and the default-visible change in the back end.
  - On the front end, wrote the stream reader (reusing Ask the Tape's parser), a pure
    reducer for the dialog's stages, the shared context, the dialog, the sidebar
    button, the panel, the notice, the hover card and three grid cells.
  - Wrote all the words in content/slotting.json "screen", the explanation, three
    decision records and the architecture rows.
  - Design choices made while building, for review:
    - The pacing runs on a timer that keeps its rhythm as events arrive, and shows
      every line at once for reduced motion.
    - Closing the dialog mid-run counts as "Go now", since the server has already
      published.
    - Cards are cached per run.
    - Keyboard users open the card by focusing the Loan ID cell.
    - The Playwright slotting spec runs as its own project after the others, because a
      run changes the shared server.
  - A real bug caught by the new end-to-end test: after a run the sidebar kept saying
    "Running…". The done event is sent while the server still holds its lock. The
    screen now marks the run finished and refreshes the status, and a Vitest case
    covers it.
- What I changed after review:
- Tests and coverage: every layer passes through `test.ps1`.
  - Back end: 536 tests, coverage 99.1%. Two new: the rules summary, and Ask the Tape
    never gets the slot columns.
  - Tests updated because their rule changed:
    - the status test, for the rules summary;
    - the new columns, now visible by default;
    - the configured-defaults test, since api.toml now names the two slot columns;
    - an agent test that built its query from that list.
  - Front end: 222 Vitest tests, 36 new: the reducer and pacing, the sentences and the
    stream, the whole flow with fake timers (including the 409 and "replaces" cases),
    the hover card, the grid cells, the column widths and the Explain switch. Tests
    updated because their rule changed:
    - the sidebar test ("Product Slotting" is a button, not Planned);
    - the width test (the 1,150 px budget stays on the tape's 12 columns).
  - End to end: 30 Playwright tests, 3 new: run from the sidebar to the updated tape,
    hover LN78265415, and filter Spec Stories. The layout and panel specs now check
    the Slotting panel instead of the note-rate axis.
- My take:

## Step 5a, the product slotting engine (back end) (2026-11-25)
- Built: Product Slotting as a run a visitor starts. `POST /api/slotting/run` slots the
  whole tape in one DuckDB pass and streams 13 steps (load, rules, three eligibility
  checks, eligible loans, coupons, one step per spec-story family, overlaps, write),
  each with a commentary line filled with real counts, then the totals. A loan is
  slotted when its program has an agency pool (UMBS or GNMA II), its product is a 30-,
  20- or 15-year fixed, and it is current; it gets a down coupon (note rate minus a 0.50
  strip, rounded down to 0.5, illustrative) and an up coupon one step higher, plus
  every spec story it fits, LLB at its lowest tier. Rules in
  `backend/app/config/slotting.toml`, words in `content/slotting.json`. One shared
  result for every visitor, in memory, behind a lock; `GET /api/slotting/status` and
  `GET /api/loans/{loan_id}/slots` (the hover card); the Loan Tape gains Slot and Spec
  Stories once a run exists. On the seeded tape: 1,467 slotted (1,012 UMBS, 455 GNMA
  II), 533 not (312 no agency pool, 85 ARMs, 136 delinquent); LLB 974 (55 at $85K), NY
  72, PR 17, Low FICO 379; 323 with more than one story; 363 generic TBA. Exactly the
  design board's numbers.
- Desk problem it solves: a tape cannot be priced until each loan is slotted. Slotting
  says which loans an agency pool will take, at which coupons, and which carry a spec
  story worth a pay-up, so Best Execution (Step 6) knows which prices to compare. The
  streamed commentary shows the desk what was checked and how many loans each check
  caught.
- My key decisions: the "5 · Product Slotting" board in Claude Design as the spec, with
  every number from the API; no slotting screen, slotting updates the Loan Tape; the
  rules and the agency map in config; the simple coupon rule (0.50 strip, round down,
  one step up); one shared result behind a lock, gone after a restart; no sleeps on the
  server, the screen paces the commentary; replace the earlier Step 5a design (slotting
  as the tape loads, nine columns, whole-loan execution) with a new commit on the same
  branch and PR; no new public sources, so the GNMA II mapping, Non-QM and the strip
  are flagged as unsourced; keep modified, forbearance and high-LTV loans slotted when
  current, to match the board.
- What Claude Code did: read the board and checked its totals against the seeded tape
  before planning (all matched); found that the branch already held a different Step 5a
  and asked how to replace it; flagged the loans a real desk would not slot, and that
  the board's coupon range "1.5 to 8.0" is the down coupons only (up runs 2.0 to 8.5).
  Wrote the config, the engine (`slotting.py`), the routes (`slotting_api.py`), the
  words, nine glossary entries, the rules page, four decision records and the
  architecture row; regenerated the OpenAPI spec and front-end types. Design choices
  made while building, for review: the coupon rounding runs on whole 0.0001% units,
  because DuckDB divides DECIMALs as floating point; the `slots` table also holds the
  grid's two text columns, so the grid filters and sorts them like any column; the
  Loan Tape switches to a view in the same step that publishes; a run stopped early or
  failing changes nothing; story steps come from spec_stories.toml, so a new family
  adds a step by itself; Ask the Tape keeps the seller's tape (a follow-up). A test
  caught a mistake in another test, which replaced text inside a comment instead of
  the `[coupons]` section line.
- What I changed after review:
- Tests and coverage: every layer passes through `test.ps1`. Back end: 534 tests (70 in
  the rewritten `test_slotting.py`: the board's totals, story counts and the
  LN78265415 card; the 13-step stream, its commentary and the done event; the tape
  before and after a run; filters and sorting on the new columns; three not-slotted
  cards and the generic TBA card; bad and unknown loan IDs; the lock (409), a lost race,
  a run stopped early, a failing run, a rerun and a restart; every loan against an
  independent pandas + Decimal reading of the config; five coupon worked examples,
  seven reason-order cases, five agency cases and seven spec-story cases; twelve bad
  configs and a bad template; words for every story and reason; unsourced rules
  flagged; a 50,000-loan run within 3 seconds and a grid page after it within the page
  budget), coverage 99.1%. The earlier design's changes to `test_api.py` were undone.
  Front end: 186 Vitest tests. End to end: 27 Playwright tests.
- My take:

## Step 4e, closing Step 4: the live eval and the new build order (2026-11-25)
- Built: the first live run of Ask the Tape's 21 golden questions, on Claude Haiku 5.5
  and Claude Sonnet 5.5, saved as `docs/evals/2026-11-25.json`. Both models got all 21
  right. Haiku costs about $0.0003 a question (3.2 seconds on average) and Sonnet about
  $0.006 (3.5 seconds). The real numbers are now in How it was built, and
  `content/agent.md`'s cost is corrected from about $0.001 to about $0.0003. A new
  decision makes slotting and best execution Loan Tape features, not screens, so the
  build order is Steps 5 and 6, then 2 and 3. The roadmap is re-forecast to 30-41
  active hours, finishing 2026-12-08 to 12-11 at 4 hours a day.
- Desk problem it solves: a desk can trust an AI tool only once it has been measured.
  The eval shows the agent gets the tape's numbers right on known answers, and what
  each question costs. Slotting on the Loan Tape means a trader slots and prices the
  loans already on screen, with no hand-off to a second grid.
- My key decisions: run both models against the same questions and tape, under the
  default $0.50 cap; keep Haiku, since Sonnet was no more accurate and cost twenty
  times as much; slotting and best execution belong on the Loan Tape; leave `nav.ts`
  for Step 5, which turns "Slotting" into a "Product Slotting" action; no "Send to
  Slotting" button on Ask the Tape; the new order 5, 6, 2, 3, 7, 8, 9.
- What Claude Code did: read the report and checked it before anything was written
  from it. The first run came back with every answer from the built-in rules, after
  the API returned 401. A length check showed the key was the 3-character
  placeholder, not the real key, and the second run was all live. Claude Code checked
  the prices in `llm.toml` against Anthropic's list and recomputed both totals by
  hand. It then wrote the How it was built paragraph, corrected the old $0.001 figure
  in `agent.md` and in two code comments (the daily cap in `llm.toml` and the eval
  script's header), recorded the decision, and updated the roadmap. It moved the 1b
  "My take" from under the template to Step 1b, unchanged. "Send to Slotting" had
  never been built, so its comment now points to the decision, and the test that
  checks it is absent keeps its check, without the "yet".
- What I changed after review: asked for the eval script to fail when every answer
  falls back, so a rejected key can never pass for an eval. It now stops with exit
  code 2, names the model and the reason (for example "http_401 x21"), and writes no
  report, so the last good one is kept. A run with only some fallbacks (the $0.50 cap
  running out partway) still counts.
- Tests and coverage: every layer passes through `test.ps1`. Back end: 464 tests (3
  new: every answer falling back stops the run with exit code 2 and leaves the last
  report untouched; some fallbacks still write the report; no results is not an
  all-fallback run), coverage 99.1%. Front end: 186 Vitest tests. End to end: 27
  Playwright tests. One Ask the Tape test was renamed, with its check unchanged.
- My take:

## Step 4d, the Agent mark and its explainer (2026-11-24)
- Built: a small gold "Agent" mark (the LoanIQ Labs flask and the word "Agent") beside
  Ask the Tape in the sidebar and beside the screen's title. Hovering it shows the new
  glossary entry "Agent" in one line. Clicking it opens a popover with
  `content/agent.md` and a new diagram, `content/diagrams/ask-the-tape-agent.svg`. The
  diagram shows the loop (question, Claude plans, guardrails, tool on DuckDB, result
  back, repeat, answer with SQL) and who does what (Claude, orchestrator, tools,
  DuckDB). The planned Tape Upload and Explorer moved to the end of the Trade group,
  after Optimizer.
- Desk problem it solves: a visitor can see which screen uses AI and, in one click,
  that Claude only plans and explains while LoanIQ's code and DuckDB produce every
  number. Without that, a trader has no reason to trust the answer.
- My key decisions: the mark is its own button after the link, never inside it; the
  explainer reuses `content/agent.md` word for word; the diagram is an image, not
  inlined markup; Tape Upload and Explorer go at the end of Trade, not in a new group.
- What Claude Code did: added `agent` to the nav items, built AgentMark and
  AgentExplainer (tooltip and popover drawn at the end of the page, so the scrolling
  sidebar cannot clip them), gave ShowcaseMarkdown an optional heading id so the
  popover is named by its own heading, drew the SVG in the app's colours, and wrote
  the tests. Tests caught two things. First, after an outside click the browser moves
  focus to the page once the click is handled, which undid the return to the mark.
  Focus now comes back after the click, and only if it did not land in another box.
  Second, the route test found links by label, and the Ask the Tape link is now
  named "Ask the Tape, agent" on purpose.
- What I changed after review:
- Tests and coverage: every layer passes through `test.ps1`. Back end: 461 tests
  (unchanged), coverage 99.1%. Front end: 186 Vitest tests (12 new: only agent items
  show the mark, outside the link, whose name says "agent"; the tooltip reads the
  glossary on hover and focus; the sidebar mark opens the explainer without
  navigating, with the diagram; an outside click closes it and returns focus, but
  never steals it from a box the visitor clicked; the title mark opens it, Esc closes
  it and focus returns; Close and a second click close it; the Agent term exists;
  five popover-placement checks. 2 updated: the sidebar test checks the Trade group's
  new order, and the route test asks for the agent link's name). End to end: 27 Playwright tests (2 new:
  the sidebar mark sits on the link's row, opens the explainer without leaving the
  Loan Tape, the diagram loads, Esc closes it and focus returns; the title mark opens
  and closes the same explainer).
- My take:

## Step 4c, Ask the Tape answers show the default loan columns (2026-11-24)
- Built: every Ask the Tape answer about specific loans now shows the 12 columns the
  Loan Tape opens with (loan ID, seller, program, product, note rate, current UPB,
  FICO, LTV, DTI, state, occupancy, DQ status), in tape order, then whatever the
  agent worked out for the question. The table is packed to its data: each column as
  wide as its widest value, tighter rows, and headers that may wrap. The list of 12
  moved from the front end to `backend/app/config/api.toml`, and both screens now
  read it from there.
- Desk problem it solves: "the largest New York loans" often came back as just loan
  ID and balance, stretched across the panel. A trader needs the seller, the coupon
  and the credit beside each loan to judge it, without opening the Loan Tape.
- My key decisions: use the same 12 columns as the Loan Tape (not a separate 10), so
  the two screens match; keep that list in one place.
- What Claude Code did: proposed two options (10 columns, or the Loan Tape's 12 moved
  to the back end). Built the server-side join for loan-level results; kept the
  model's view, the stored SQL and the Open in Loan Tape link exactly as the agent
  wrote them; added the `default_visible` flag to the columns API; and packed the
  table with CSS. Tests caught two issues on the way. First, the configured list was
  not in tape order (state sits after note rate on the tape), although the old
  comment said it was. Both screens now follow tape order. Second, the committed
  OpenAPI spec had to be regenerated after the column model changed.
- What I changed after review:
- Tests and coverage: every layer passes through `test.ps1`. Back end: 461 tests (8
  new: the default columns are joined on in tape order with the agent's row order
  kept and the tape's values; the model and the SQL are unchanged; grouped,
  repeated-loan, repeated-column and empty results are left alone; nothing is
  duplicated when the agent already chose the columns; the API marks the configured
  defaults; unknown and repeated names in the config are dropped; 1 updated, the
  column JSON now includes `default_visible`), coverage 99.1%. Front end: 174 Vitest
  tests (1 new: the result table shows the 12 columns and the agent's own in order,
  in tape formats; 1 updated, the width check now reads the list from `api.toml`;
  test fixtures gained the new field). End to end: 25 Playwright tests (1 new: a
  loan-level answer shows the 12 default columns, and FICO and State stay narrower
  than 70 px at 1440 px).
- My take:

## Step 4b, the Ask the Tape screen (2026-11-24)
- Built: the Ask the Tape screen, built to the "Ask the Tape" design board. A trader
  types a question, or picks an example. The answer streams in with a chip for each
  tool the agent called; clicking a chip shows the exact SQL it ran. Under the answer
  are the rows behind it, formatted like the Loan Tape. Every loan ID, in the answer
  or the table, opens a drawer with all of that loan's fields, read by the agent's
  own `get_loan` tool. "Open in Loan Tape" opens the full grid with the same filter
  and sort, written as ordinary column filters. When a filter can't be written that
  way, the button says why. "Save query" keeps the answer's SQL in the browser (the
  last 5), and one click reruns it with no AI model. A small "Offline" banner shows
  when built-in rules are answering. The header's "Ask the tape" box and Ctrl K open
  the screen with the question filled in but not sent. Ask the Tape is now live in
  the sidebar. Back end: `GET /api/ask/status`, `GET /api/ask/loans/{id}`,
  `POST /api/ask/rerun`, a Loan Tape link on every query result, and the grid's
  number filter gains "or equal" and "not equal". When a model call fails, the log
  now has the provider's own message and status, never the key or the question.
- Desk problem it solves: the answer is a starting point, not a dead end. From one
  question the trader can check the SQL, inspect a single loan, take the slice into
  the full grid to keep working, and rerun the same question on the next tape for
  free.
- My key decisions: build to the design board, with tool chips that show their SQL,
  a loan drawer, "Open in Loan Tape" from the URL, saved queries rerun without the
  model, an Offline banner, and Ctrl K. "Send to Slotting" stays hidden until Step
  5. The answer's filter is translated into the grid's own column filters, and is
  refused with a reason rather than approximated. Saved queries live in the browser
  and rerun through the same guardrails as the model's SQL. Every result is a plain
  table for now. Model errors are logged with the provider's message. Reasons:
  docs/decisions.md.
- What Claude Code did: read the design board on the canvas and the Step 4a engine,
  proposed the plan and three decisions, then built the back-end routes and the SQL
  to grid-filter translation, the screen and its components, the content and
  glossary entries, and the tests, and ran every layer. Along the way:
  - The redaction test caught a real bug: "Authorization: Bearer tok123" kept the
    token, because the pattern took "Bearer" as the value. The pattern now removes
    the token.
  - The first end-to-end run found two ambiguous locators: AG Grid's floating filter
    has its own "Clear" button, so the Loan Tape's button became "Show the whole
    tape", and the Offline notice appears in the banner and under the answer.
  - Existing tests changed only where the requirement changed: Ask the Tape is live
    in the sidebar and routes, the header box is enabled instead of disabled, and
    "not equal" is now a supported grid filter (the rejection case moved to
    "notBlank").
- What I changed after review:
- Tests and coverage: every layer passes through `test.ps1`. Back end: 452 tests
  (59 new: the SQL to grid-filter translation, each operator and each refusal, and
  a check that the grid counts the same loans as the agent's SQL; the status, loan
  and rerun routes and their guardrails; the new grid operators; provider error
  logging with keys and questions removed; the screen's tool list matching the
  agent's), coverage 99.1%. Front end: 173 Vitest tests (49 new: the stream reader,
  the turn model, saved queries, the Loan Tape URL, formatting, the screen's whole
  loop, the header box and Ctrl K, the Loan Tape's filter from the URL). End to
  end: 24 Playwright tests (6 new, on the built-in rules).
- My take:

## Step 4a, the Ask the Tape engine (back end) (2026-11-23)
- Built: the engine behind Ask the Tape, following the design in content/agent.md.
  A visitor's question goes to Claude Haiku 5.5, which plans and explains; five
  LoanIQ tools (list columns, query the tape, summarize it, look up a term, get one
  loan) do every calculation in DuckDB. Every query the model writes is checked
  first: one SELECT, known columns, the loans table only, values bound as
  parameters, at most 500 rows and 2 seconds, on a read-only copy of the tape. A
  refused query goes back to the model with the reason; after two refusals the
  question moves to Claude Sonnet 5.5. A question gets at most 5 rounds and 20
  seconds. Built-in rules answer when there is no key, when the model fails or
  declines, when the day's budget or the visitor's limit is used up, and always for
  desk-question chips; the answer says which. `POST /api/ask` streams each step with
  its SQL, the answer and its cost; `GET /api/ask/queries/{id}` returns every row
  behind an answer. Every question's tokens and dollars are logged. ChatGPT and
  Gemini sit behind the same interface, off until a key is set. Golden questions
  (21, each graded against the tape's true answer) pass in CI on a scripted model,
  and `backend\scripts\eval_agent.py` runs them on live models with accuracy,
  tokens and cost per model.
- Desk problem it solves: a trader can ask the tape a question in plain English
  ("WAC of the New York loans?") and get the tape's real number with the SQL behind
  it, instead of writing the query or filtering the grid by hand.
- My key decisions: Claude Haiku 5.5, escalating to Sonnet 5.5 after two refused
  calls, built-in rules as the fallback; the model never does the math and sees only
  totals plus 20 rows; limits of 5 rounds, 800 output tokens and 20 seconds; a daily
  dollar cap and a per-visitor limit; one provider interface so the model can be
  swapped; all three vendor SDKs pinned. Reasons: docs/decisions.md.
- What Claude Code did: proposed the plan; checked the installed SDKs, FastAPI's
  built-in SSE and DuckDB's read-only settings before writing code; built the
  engine, the five adapters, the guardrails, the budget, the golden questions, the
  eval script and 161 new tests. Along the way: the first guard tests showed that
  sqlglot's tree walk does not follow the order the SQL is printed in, so positional
  `?` values could bind to the wrong column; the guard now uses named parameters
  ($p1, $p2) and a test checks each value sits next to its own column. A grading
  test showed the first rounding rule let 6.5% pass for a true WAC of 6.41%; the
  grader now requires a correct rounding at the precision written.
- What I changed after review: asked for all three SDKs to be pinned.
- Tests and coverage: every layer passes through `test.ps1`. Back end: 393 tests
  (161 new: guardrails and the read-only tape, tools, budget and config, the five
  adapters against each SDK's real response types, the orchestrator's limits and
  fallbacks, the streamed API, the golden questions on the Fake, the grader and the
  eval script), coverage 99.2%. Front end: 124 Vitest tests (no change). End to end:
  18 Playwright tests (no change). The screen comes in Step 4b.
- My take:

## Step 1g, closing Step 1: the Loan Tape at 1440 px (2026-11-23)
- Built: the Step 1d layout follow-ups, checked against the "1 · Loan Tape" board,
  which is drawn at 1440 px. The 12 default grid columns now start at widths fitted
  to their content, not 130 px each, so all 12 show at 1440 px with nothing cut off.
  The explanation panel starts closed and opens with one click. The note-rate panel
  has the board's caption, "UPB by 0.5% bucket", and its title stays on one line. Its
  axis reads 2.0% / 4.0% / 6.0% / 8.0% / 9%+, with the ticks centred on their bucket
  edges and the last label at the right end. The "Desk questions" label sits above
  the chips, so all six chips fit on one row. The logo update (house-and-coin flask)
  was committed on its own first.
- Desk problem it solves: on a 1440 px laptop a trader sees the whole default tape
  (who sold it, what it is, coupon, balance, credit, status, occupancy) without
  scrolling sideways, and the panels and chips read cleanly.
- My key decisions: the explanation closed by default; the "Desk questions" label on
  its own line instead of smaller chips or a narrower sidebar; about 8 columns
  visible when the explanation is open. Reasons: docs/decisions.md.
- What Claude Code did: proposed the plan; measured the screen in Chromium at 1440 px
  before and after each change; read the board from the design canvas and measured
  the board's own table (about 1,100 px for 12 columns, so it too scrolls beside the
  explanation); tuned the column widths until nothing was cut off; wrote the tests.
  Along the way: the three files I expected to need converting to LF were already
  LF, so the logo commit needed no conversion; the first axis fix (right-aligning
  "9%+") still overlapped "8.0%" with the explanation open, so the middle ticks are
  centred on their bucket edges instead; a CSS rule for the axis columns also
  matched the new label text inside them, until it was limited to direct children;
  the first run of the new browser test read headers in upper case (innerText
  applies CSS), so it reads textContent instead.
- What I changed after review: asked for the explanation panel to be off by default.
- Tests and coverage: every layer passes through `test.ps1`. Back end: 232 tests (no
  change), coverage 98.8%. Front end: 124 Vitest tests (7 new: the default column
  widths and their 1440 px budget, the bucket width, the short open-ended label, the
  panel caption and the axis label placement; 2 updated: the explanation now starts
  closed, and the axis reads "9%+"). End to end: 18 Playwright tests (2 new, at
  1440 px with the explanation closed and open: columns that fit, a one-line title,
  chips on one row, the axis labels apart; 1 updated: the explain test opens the panel
  first).
- My take:

## Brand update, the house-and-coin flask (2026-11-23)
- Built: a new LoanIQ Labs symbol. The flask stays; inside it a house with a gold $
  coin stands in blue liquid, replacing the brain. It is in the header logo, the
  About page logo, the browser-tab favicon and the app icons.
- Desk problem it solves: the logo now points to home loans, the asset the whole
  app is about.
- My key decisions: a lab flask close to the old symbol with a house and coin
  inside; the On-navy version; no hand; only the files the site uses for now (the
  light, mono and PNG logos later); I review, test, commit and push myself.
- What Claude Code did: nothing this time. Claude in Cowork drew four symbol
  concepts in three styles on a Claude Design canvas, then the flask version,
  swapped the symbol into the two site logos (lettering untouched), generated the
  icons and updated brand/README.txt and docs/decisions.md.
- What I changed after review: asked for the flask to stay close to the previous
  symbol with the house-and-coin icon inside; had the hand removed because it did
  not look like a hand; picked the On-navy version.
- Tests and coverage: file names are unchanged, so no new tests.
- My take:

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
- My take: A trader slicing a seller’s tape shouldn’t have to wait on the screen, and the browser shouldn’t hold every loan. So the server does the paging, sorting, filtering and pool math in DuckDB, and no page can be bigger than 500 rows. The definitions matter as much as the speed: delinquent means any status other than Current, so the summary count is the conservative number a desk would quote, and I corrected the glossary’s LTV formula to match the tape. Claude Code wrote the API and 60 tests quickly, including SQL injection attempts. My part was setting the limits and the 300 ms budget (a deep page of a 50,000-loan tape comes back in about 150 ms) and checking that each number means what a desk expects.

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
- My take:
