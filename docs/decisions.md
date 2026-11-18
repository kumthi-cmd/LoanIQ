# Decisions
One entry per design decision, newest first.

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
