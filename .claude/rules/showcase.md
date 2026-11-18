# Showcase: every screen explains itself
The reader is a capital markets or technology professional seeing LoanIQ for the first
time. Every step must help them see three things: how the mortgage capital markets
workflow works, how each screen supports it, and how the app was built AI-first.

## Visitor-facing words live in content/
- The app renders files from content/. Never hard-code explanations in components.
- One fact in one place: each term is defined once, in content/glossary.json.

## Business rules come from public sources
- Every business rule, threshold and price grid must trace to a public industry source:
  regulators, industry associations, the agencies' public guides, or textbooks.
  Record it in docs/public-sources.md.
- Label every threshold and price as illustrative, in config and on screen.
- If you can't name a public source for a rule, say so and use a generic alternative.

## Every screen ships with its explanation
- content/screens/<screen>.md has two sections:
  "## Business": what the desk uses this screen for, which decisions it supports, and
  why the numbers matter. Plain English, no code.
  "## Technical": how the screen gets its data, the main components, and the design
  choices and trade-offs.
- Every new term on a screen gets a glossary entry: term, definition, why it matters.

## About and How it was built
- content/about.md describes LoanIQ: what it does, the approach and the architecture.
  Suggest changes to it and wait for my OK; don't rewrite it yourself.
- content/how-it-was-built.md explains the AI-first approach. Update it when the way we
  work changes.

## Build log
At the end of every step, add an entry to content/build-log.md using its template: what
we built, the desk problem it solves, my key decisions, what Claude Code did, what I
changed after review, and tests and coverage. Leave "My take" for me to write.
