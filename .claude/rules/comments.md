# Comments: I learn by reading the code
Comment heavily. I need to understand both the business meaning and the technical approach.
- Every file starts with a header comment: what the file does, where it sits in the LoanIQ
  flow, the business purpose, and the main technical choices and why they were made.
- Every function, class and React component has a docstring (Python) or JSDoc (TypeScript)
  with two labelled parts:
  BUSINESS: what it means for a capital markets desk (for example, why LTV > 125 matters).
  TECH: how it works, inputs and outputs with units, edge cases, and what can go wrong.
- Inside functions, comment each logical block, not each line. Say why, not just what.
- Label inline comments "BUSINESS:" or "TECH:" so I can scan for either.
- Spell out every formula in mortgage terms (amortization, weighted averages, LTV, coupon
  slotting) with units: percent or decimal, dollars, months, 32nds.
- The first time a library or language feature appears (FastAPI routes, DuckDB parameters,
  pandas vectorization, React hooks, AG Grid data sources), explain it in a short comment.
- Comment tests with the business rule each one protects.
- When you change code, update its comments in the same edit.
