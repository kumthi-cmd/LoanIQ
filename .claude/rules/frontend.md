---
paths:
  - "frontend/**"
---
# Front end (the SPA)
- React + TypeScript + Vite, React Router for screens, AG Grid Community for grids.
- Types for API data come from the back end's OpenAPI spec, with no hand-written copies.
- Numbers right-aligned with tabular numerals. Money with commas, rates with 3 decimals,
  LTV and DTI with 2, prices also in 32nds (101-16+ = 101.515625).
- Color only for meaning: delinquency, P&L sign, limit status.
- Every screen has an "Explain this screen" panel and glossary tooltips (showcase.md).
- One component per file, named for what it shows.
