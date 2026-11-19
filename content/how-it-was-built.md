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
4. The tests gate the start of the app. I commit, and GitHub runs the tests again.

One script, `test.ps1`, runs every layer: back-end tests with coverage, front-end
type checks and component tests, the production build, and browser tests that click
through the built app the way a visitor would. `start.ps1` runs it first and starts
LoanIQ only if everything passes.

## By the numbers
Tests, coverage and commits, filled in from content/build-facts.json.
