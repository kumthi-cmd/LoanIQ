# LoanIQ
A single-page web app (SPA) for mortgage capital markets:
loan tape -> slotting -> best execution -> positions and optimizer -> pool candidates.
All data is synthetic. No real borrowers, names or addresses.

## Purpose
LoanIQ shows a mortgage capital markets workflow end to end. Every screen explains itself
in business and technical terms, and the app shows how it was built: AI-first engineering
with Claude Code in VS Code. Build every step so a capital markets or technology
professional seeing LoanIQ for the first time can follow it.

## Map: read these when the task needs them
- Architecture and data flow: `docs/architecture.md`
- Current step and what's next: `docs/roadmap.md`
- Design decisions and why: `docs/decisions.md`. Add an entry for each new decision.
- Public sources behind every business rule: `docs/public-sources.md`
- Mortgage terms: `content/glossary.json`
- Loan tape fields, types and units: `docs/domain/loan-tape-schema.md` (from Step 1)
- Slotting rules: `docs/domain/slotting-rules.md` (from Step 5)
- Visitor-facing pages and screen explanations: `content/`
Rules in .claude/rules/ load by themselves: comments, testing and showcase always;
python, frontend and e2e when working in those folders.

## Always
- I'm learning. Show a short plan and wait for my OK before writing code.
- Build only the step I ask for. Explain each new file in plain English afterwards.
- Every change comes with tests. Run them before saying a step is done.
  Never weaken, skip or delete a test to make it pass.
- Comment heavily with BUSINESS: and TECH: notes (.claude/rules/comments.md).
- Every screen ships with its explanation, and every step ends with a build-log entry
  (.claude/rules/showcase.md).
- Business rules come from public industry sources, recorded in docs/public-sources.md.
  Label every threshold and price as illustrative.
- Ask me before adding any new source to docs/public-sources.md.
- Every random process takes a seed. Never build SQL from user input; use parameters.
- Never commit .env or secrets.
- I use Windows 11 and PowerShell. Give me PowerShell commands, not bash.

## Keep facts in one place
Don't copy a fact into a second file; point to where it lives. Thresholds and limits live
in the code's config. If two files disagree, tell me instead of picking one.
