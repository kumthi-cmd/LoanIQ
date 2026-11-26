# Roadmap
Current step: Step 5c done (2026-11-25): Ask the Tape's scope grows with the desk.
The agent knows the tape from the start and each stage once the desk has run it
(backend/app/agent/stages.py): after a Product Slotting run its read-only copy is rebuilt
with flat slot columns, it gets a short Slotting prompt section and the explain_slot tool,
and Ask the Tape shows the stages it knows. Step 5 (5a engine, 5b Loan Tape action, 5c
agent) is done. Next: Step 6, the price file and best execution on the Loan Tape, which
plugs into the same stages.
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
| 5 Slotting rules engine on the Loan Tape | Done: 5a engine, 5b Loan Tape action, 5c agent stages | 3-4 | 8 (5a: 3, 5b: 1, 5c: 4) |
| 6 Price file and best execution on the Loan Tape | Not started | 5-7 | |
| 2 Tape upload and parser | Not started | 3-4 | |
| 3 Explorer | Not started | 2-3 | |
| 7 Blotter and position monitor | Not started | 6-8 | |
| 8 Optimizer and pool candidates | Not started | 7-10 | |
| 9 Polish and publish | Not started | 3-4 | |

## Pace and forecast
Estimates set 2026-11-19, after Step 1d; re-forecast 2026-11-25 after Step 4 ran 50%
over its estimate (10.5 active hours against 5-7), and again 2026-11-25 after Step 5
ran twice its estimate (8 against 3-4). Most of Step 5's overrun is scope added along
the way, not slower work: 5c (the agent's scope growing with the desk, 4 hours) was not
in the original estimate. Active hours are time spent building, including design and
review.

- Pace so far: Steps 4 and 5 took 18.5 active hours against estimates of 8-11, about
  1.7 times the estimate. Steps 0 to 1 ran close to theirs.
- Left at the estimates: about 26-36 active hours (Steps 6, 2, 3, 7, 8 and 9), plus
  about 2-3 for the simple Postgres planned before trading (docs/decisions.md).
- Forecast at 4 hours a day, weekdays from 2026-11-30 (Thanksgiving Thursday and Friday,
  2026-11-26 and 27, off): at the estimates, around 2026-12-09 to 2026-12-11; if later
  steps also run about 1.5 times over, around 2026-12-14 to 2026-12-18.
- At 2.5 hours a day: around 2026-12-15 to 2026-12-21 at the estimates, and around
  2026-12-22 to 2026-12-31 at 1.5 times.
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
- Done (Step 5b): the sidebar's "Slotting" item is the Product Slotting action; Slot
  and Spec Stories show by default after a run; the screen paces the commentary.
- Slot and Spec Stories have no glossary tooltips on their headers yet: the grid reads
  tooltips from content/loan-columns.json only.
- Done (Step 5c): Ask the Tape sees Product Slotting once it has run, with six golden
  questions on slots.
- Not modelled: modified, forbearance and high-LTV loans treated separately; seasoning;
  per-agency fees; ARM pools; pool-level limits (pooling is Step 8).
- Find public sources for the three rules listed under "Rules without a recorded
  source" in docs/public-sources.md.

From Step 5c (Ask the Tape's stages, 2026-11-25):
- content/agent.md: one line saying the agent's scope grows with the desk, and
  explain_slot in its tool list (wording waiting for approval).
- Run scripts\eval_agent.py live on Claude Haiku 5.5 (28 questions at their stages,
  about $0.01) and record accuracy and cost; needs ANTHROPIC_API_KEY.
- Step 6 plugs best execution into the same stages: a contribution in main.py, a
  prompt file, its tools and golden questions.
- Results live in memory: a restart forgets slotting and the agent's stages until the
  desk reruns it. A simple Postgres comes with the paid Render plan, before Step 7.

From Step 5b (Product Slotting on the Loan Tape, 2026-11-25):
- The board's "NEW" badges on the Slot and Spec Stories headers are not drawn (they
  need a custom AG Grid header component); the two columns are tinted instead.
- components/NoteRatePanel.tsx and its tests are kept but no longer drawn; decide in
  Step 6 whether the note-rate buckets come back (the API still sends them).
- The confirm dialog shows loans and fields, not the board's as-of date and seed: the
  generator could write them beside the tape if wanted.

From Step 4b (Ask the Tape screen, 2026-11-24):
- A chart for grouped answers (the board's "90+ by seller" bars); every result is a
  table for now.
- "Open in Loan Tape" cannot show a list of more than two values in one column
  (for example the five 90+ statuses). A grid "in list" filter would cover it.
- Check a failed model call on Render shows the new `provider_error` log line with
  the provider's message.

At the end of each step, update its status and actual hours. If a step runs more
than 25% over its estimate, re-forecast the finish date.
