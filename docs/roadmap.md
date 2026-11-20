# Roadmap
Current step: 1. Done: 1a synthetic loan tape generator, 1b loan API, 1c SPA and loan grid, 1d Loan Tape screen to the design board (panels, desk questions, explain tabs). Next: About page.

| Step | Status | Estimate (active hours) | Actual (active hours) |
| --- | --- | --- | --- |
| 0 Setup | Done | 0.5 | 1 |
| 1 Loan tape, fast grid, About page | In Progress | 10-11 | 7.5 so far |
| Hosting: live site, deploy on every push | Not started | 4-6 | |
| 2 Tape upload and parser | Not started | 3-4 | |
| 3 Explorer | Not started | 2-3 | |
| 4 Ask the Tape agent | Not started | 5-7 | |
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
  How it was built pages, the CI workflow, "My take" entries, the Loan Tape polish
  follow-ups below, merge to main).
- Forecast at 4 hours a day: 10-14 build days, finishing around 2026-12-07 to
  2026-12-11 (weekdays, Thanksgiving Thursday and Friday off). At 2.5 hours a day:
  around 2026-12-15 to 2026-12-23.
- The high end of each estimate assumes a design pass like the Loan Tape screen's.
  The design canvas has boards for Ask the Tape, Slotting & Best Execution,
  Blotter & Positions and the Optimizer.
- Hosting comes right after Step 1, so every later step goes live on push and
  deployment problems show up while the app is small (decided 2026-11-19). Start on
  the host's free address, then add the domain LoanIQLabs.com (registered 2026-11-19 at Namecheap)
  before the link goes on any application.
- Risk: plan usage limits can slow the agent (Step 4) and optimizer (Step 8)
  steps. Run routine sub-steps on Sonnet.

## Open follow-ups
Small items noted at the end of a step, to come back to.

From Step 1d (Loan Tape screen to the design board, 2026-11-19):
- Grid width: at 1440 px with the explanation open, only about 6 of the 12 default
  columns fit before the grid scrolls sideways.
- Note-rate axis: the "8.0%" and "9.0%+" labels sit very close together.
- Wrapping: the "Note rate distribution" title wraps to two lines, and the
  Forbearance chip drops to a second row. The design shows each on one line.
- e2e: the "planned screens" test finds sidebar items by their `aria-disabled`
  attribute; `.claude/rules/e2e.md` asks for role and visible text.

At the end of each step, update its status and actual hours. If a step runs more
than 25% over its estimate, re-forecast the finish date.
