# How LoanIQ was built: AI-first engineering

## The approach
LoanIQ was built with Claude Code in VS Code. I acted as product owner and engineering lead:
I set the standards, broke the work into steps, approved each plan and reviewed every
change. Claude Code wrote the code and the tests under those standards.

## The standards Claude Code works to
- CLAUDE.md: purpose and the rules for every task
- Comments: every function explains its business meaning and its technical design
- Tests: written with every change; the app won't start unless they pass
- Showcase: every screen ships with its own explanation

## The loop for every step
1. I describe the step and how we'll know it's done.
2. Claude Code proposes a plan, and I approve or change it.
3. Claude Code builds and tests, and I review every change.
4. The tests gate the start of the app. I commit and push, GitHub runs the tests again,
   and only a green `main` goes live.

Screens are designed before they are built. I lay each screen out on a Claude Design
canvas, one board per screen, with sample numbers. Claude Code reads the board,
compares it with what the repo already has, and proposes what to reuse, change and
add. The build then matches the board's layout, colors and fonts, but every number
on screen comes from the API, never from the design's samples.

From the Price Grid (Step 6c), a board can also start from the plan. When no board
exists yet, Claude draws one on a Claude Design canvas from the agreed plan, in the
Loan Tape's colours and with that day's live numbers, and I review it, and change
it if needed, before any code is written. Clicking through a working design catches
layout questions a text sketch can't.

One script, `test.ps1`, runs every layer: back-end tests with coverage, front-end
type checks and component tests, the production build, and browser tests that click
through the built app the way a visitor would. `start.ps1` runs it first and starts
LoanIQ only if everything passes.

The live site follows the same rule. Every push runs the same layers again on GitHub
Actions, on a clean Linux machine, then builds the exact container the host will run,
starts it and checks that the tape loaded and the screens load. Render deploys `main`
only after all of that passes, and switches visitors to the new version only once it
reports healthy. A test fails if the GitHub workflow and `test.ps1` stop running the
same checks, so "green" means the same thing on my PC and online.

An AI feature is tested like any other, plus one more gate. Ask the Tape's guardrails,
tools and fallbacks are tested on every run with a scripted model that costs nothing.
A set of golden questions, each with its true answer computed from the tape, must all
pass that way too. Before a release, or a change of model, the same questions run on
the live model, and a report shows how many it got right, how many tokens it used and
what it cost.

The first live run, on 2026-11-25, put two models through the same 21 questions on
the same tape (`docs/evals/2026-11-25.json`). Claude Haiku 5.5 got all 21 right, at
about 5,400 tokens and $0.0003 a question, in 3.2 seconds on average. Claude Sonnet
5.5 also got all 21 right, at about 6,100 tokens and $0.006 a question, in 3.5
seconds. About 70% of the input tokens came from the prompt cache.
Sonnet was no more accurate, cost twenty times as much and was slightly slower, so
Ask the Tape stays on Haiku. Prices are illustrative, from Anthropic's price list.

When the agent learned Product Slotting (Step 5c), the golden set grew to 28
questions, each asked at its stage of the desk: the tape's 21 and "how many loans are
slotted?" before a run, where the right answer is that slotting has not run yet, then
six slot questions after it (`docs/evals/2026-11-25-5c.json`). Haiku got 27 of 28, at
$0.00028 a question. Every slot question passed, including "why isn't LN79962194
slotted?", answered from the loan's slot card. The one miss was right but written in
words: "Twenty loans have an LTV over 125%", which the grader, reading digits only,
could not check. The fix was a one-line rule in the agent's prompt (write every number
in digits), not a looser grader. The rerun got all 28 right, at $0.00027 a question
(`docs/evals/2026-11-25-5c-digits.json`).

## By the numbers
Every time all the test layers pass on my PC, `test.ps1` counts the tests in each layer,
reads the back-end coverage and counts the commits, and writes them to
`content/build-facts.json`. I commit that file, so the live site shows the numbers from
the last full test run. The commit count is taken before that run's own commit.
