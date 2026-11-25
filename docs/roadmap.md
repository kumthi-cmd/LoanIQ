# Roadmap
Current step: Step 5a done (2026-11-25): the product slotting engine (back end).
Every loan is slotted as the tape loads (Agency, Whole loan or Not deliverable; UMBS
or Ginnie Mae II; product; base, down and up coupons; spec stories), from the rules in
backend/app/config/slotting.toml, explained in docs/domain/slotting-rules.md. Two new
routes: GET /api/loans/slotting and GET /api/slotting/rules. Next: Step 5b, the
Product Slotting action and the read-only Slotting rules popup on the Loan Tape.
Step 4e (live eval, new build order) is in PR #8.
Hosting is done: LoanIQ is live at https://www.loaniqlabs.com, deployed from `main`
after CI passes. Step 1 delivered: 1a synthetic loan tape generator, 1b loan API,
1c SPA and loan grid, 1d Loan Tape screen to the design board (panels, desk
questions, explain tabs), 1e LoanIQ Labs brand (house-and-coin flask from
2026-11-23), 1f About and How it was built pages (with "By the numbers" from
content/build-facts.json), 1g the Loan Tape layout at 1440 px (the 1d follow-ups).
"My take" entries in content/build-log.md are still to write.

| Step | Status | Estimate (active hours) | Actual (active hours) |
| --- | --- | --- | --- |
| 0 Setup | Done | 0.5 | 1 |
| Hosting: live site, deploy on every push | Done | 4-6 | 1 |
| 1 Loan tape, fast grid, About page | Done | 10-11 | 11 |
| 4 Ask the Tape agent | Done: 4a engine, 4b screen, 4c answer columns, 4d Agent mark, 4e live eval | 5-7 | 10.5 (4a: 3, 4b: 4, 4c: 1, 4d: 1.5, 4e: 1) |
| 5 Slotting rules engine on the Loan Tape | In progress: 5a engine done; 5b Loan Tape action next | 3-4 | 2 (5a: 2) |
| 6 Price file and best execution on the Loan Tape | Not started | 5-7 | |
| 2 Tape upload and parser | Not started | 3-4 | |
| 3 Explorer | Not started | 2-3 | |
| 7 Blotter and position monitor | Not started | 6-8 | |
| 8 Optimizer and pool candidates | Not started | 7-10 | |
| 9 Polish and publish | Not started | 3-4 | |

## Pace and forecast
Estimates set 2026-11-19, after Step 1d; re-forecast 2026-11-25, after Step 4 ran
50% over its estimate (10.5 active hours against 5-7). Active hours are time spent
building, including design and review.

- Pace so far: Steps 0 to 1d took about 8.5 active hours over 2026-11-18 and
  2026-11-19, about 4 a day. Step 1 is running about 1.5 times faster than the
  build guide's two to three evenings.
- Left: about 30-41 active hours (Steps 5, 6, 2, 3, 7, 8 and 9).
- Forecast at 4 hours a day: finishing around 2026-12-08 to 2026-12-11. At 2.5 hours
  a day: around 2026-12-14 to 2026-12-21. Weekdays only, with Thanksgiving Thursday
  and Friday (2026-11-26 and 27) off.
- The high end of each estimate assumes a design pass like the Loan Tape screen's.
  The design canvas has boards for Ask the Tape, Slotting & Best Execution,
  Blotter & Positions and the Optimizer.
- Hosting comes early, so every later step goes live on push and deployment problems
  show up while the app is small (decided 2026-11-19). On 2026-11-20 it moved ahead of
  the About page: one Docker container on Render (docs/decisions.md). Render's free
  plan for now. Before the link goes on any application: upgrade to Starter
  ($7/month; change `plan` in render.yaml).
- Risk: plan usage limits can slow the agent (Step 4) and optimizer (Step 8)
  steps. Run routine sub-steps on Sonnet.

## Open follow-ups
Small items noted at the end of a step, to come back to.

From Hosting (2026-11-20):
- Timing tests fail on battery power (the Surface slows its CPU). Run `test.ps1`
  plugged in.
- The image holds the test tools from requirements.txt (pytest and friends, a few
  MB). Split into a runtime and a dev requirements file if the image size matters.

From Step 1f (About and How it was built, 2026-11-23):
- Commit content/build-facts.json after each green `test.ps1` run, so the live site's
  "By the numbers" stays current.
- Redesign How it was built around three parts: approach, architecture and design.

From Step 4a (Ask the Tape engine, 2026-11-23):
- Done: ANTHROPIC_API_KEY set in the Render dashboard (Environment).
- Done (Step 4e, 2026-11-25): ran `backend\scripts\eval_agent.py` on Claude Haiku 5.5
  and Sonnet 5.5 (docs/evals/2026-11-25.json).
- Stream the answer word by word if the whole-answer event feels slow on screen.

From Step 5a (slotting engine, 2026-11-25):
- Step 5b: decide the sidebar's planned "Slotting" item (remove it, or link to the
  Loan Tape with slotting on).
- Slot columns have headers but no glossary tooltips on the Loan Tape yet: the grid
  reads tooltips from content/loan-columns.json only. Step 5b reads
  content/slotting.json "terms" too.
- A golden question about slots (say, loans in UMBS 30 at a 6.0 coupon), so the eval
  covers the new columns.
- Not modelled: seasoning (older loans into seasoned pools) and pool-level limits
  such as the High-Balance share of a TBA pool (pooling is Step 8).

From Step 4b (Ask the Tape screen, 2026-11-24):
- A chart for grouped answers (the board's "90+ by seller" bars); every result is a
  table for now.
- "Open in Loan Tape" cannot show a list of more than two values in one column
  (for example the five 90+ statuses). A grid "in list" filter would cover it.
- Check a failed model call on Render shows the new `provider_error` log line with
  the provider's message.

At the end of each step, update its status and actual hours. If a step runs more
than 25% over its estimate, re-forecast the finish date.
