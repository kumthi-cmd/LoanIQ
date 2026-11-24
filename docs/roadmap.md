# Roadmap
Current step: Step 4b done (2026-11-24), the Ask the Tape screen, on branch
`step-4b` (PR into `main`). Step 4a, the engine, is merged into `main`. Step 4 was
taken ahead of Steps 2 and 3.
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
| 2 Tape upload and parser | Not started | 3-4 | |
| 3 Explorer | Not started | 2-3 | |
| 4 Ask the Tape agent | Done: 4a engine, 4b screen | 5-7 | |
| 5 Slotting rules engine | Not started | 3-4 | |
| 6 Price file and best execution | Not started | 5-7 | |
| 7 Blotter and position monitor | Not started | 6-8 | |
| 8 Optimizer and pool candidates | Not started | 7-10 | |
| 9 Polish and publish | Not started | 3-4 | |

## Pace and forecast
Estimates set 2026-11-19, after Step 1d. Active hours are time spent building,
including design and review.

- Pace so far: Steps 0 to 1d took about 8.5 active hours over 2026-11-18 and
  2026-11-19, about 4 a day. Step 1 is running about 1.5 times faster than the
  build guide's two to three evenings.
- Left: about 41-56 active hours, including about 3 to finish Step 1 (About and
  How it was built pages, "My take" entries, the Loan Tape polish follow-ups below).
  The CI workflow and the merge to main moved into Hosting.
- Forecast at 4 hours a day: 10-14 build days, finishing around 2026-12-07 to
  2026-12-11 (weekdays, Thanksgiving Thursday and Friday off). At 2.5 hours a day:
  around 2026-12-15 to 2026-12-23.
- The high end of each estimate assumes a design pass like the Loan Tape screen's.
  The design canvas has boards for Ask the Tape, Slotting & Best Execution,
  Blotter & Positions and the Optimizer.
- Hosting comes early, so every later step goes live on push and deployment problems
  show up while the app is small (decided 2026-11-19). On 2026-11-20 it moved ahead of
  the About page: one Docker container on Render (docs/decisions.md). Render's free
  plan and free address for now. Before the link goes on any application: upgrade to
  Starter ($7/month; change `plan` in render.yaml) and add the domain LoanIQLabs.com
  (registered 2026-11-19 at Namecheap).
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
- Run `backend\scripts\eval_agent.py` on Claude Haiku 5.5 once the key is set, to
  measure real accuracy, tokens, cache hits and cost per question (content/agent.md
  says about $0.001; the estimate is $0.001-0.002).
- Stream the answer word by word if the whole-answer event feels slow on screen.

From Step 4b (Ask the Tape screen, 2026-11-24):
- Step 5: add "Send N loans to Slotting" under each answer's table (on the design
  board, hidden until Slotting exists).
- A chart for grouped answers (the board's "90+ by seller" bars); every result is a
  table for now.
- "Open in Loan Tape" cannot show a list of more than two values in one column
  (for example the five 90+ statuses). A grid "in list" filter would cover it.
- Check a failed model call on Render shows the new `provider_error` log line with
  the provider's message.

At the end of each step, update its status and actual hours. If a step runs more
than 25% over its estimate, re-forecast the finish date.
