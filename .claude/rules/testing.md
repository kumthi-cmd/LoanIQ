# Testing
- Every change comes with tests, in the same step.
- Back end: pytest in backend/tests. Unit tests for formulas and rules, API tests with
  FastAPI's TestClient, and timing tests for anything that must be fast.
- Front end: Vitest with React Testing Library, next to the code as *.test.ts(x).
- End to end: Playwright in e2e/, against the built SPA at http://localhost:8000.
- test.ps1 runs every layer. Keep back-end coverage at 80% or more.
- start.ps1 runs test.ps1 first and refuses to start if anything fails.
- Never weaken, skip or delete a test to make it pass. If a test fails, find the cause
  and tell me what it was.
