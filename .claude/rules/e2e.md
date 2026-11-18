---
paths:
  - "e2e/**"
---
# End-to-end tests (Playwright)
- Test what a visitor does: open a screen, filter, open the explain panel, read a number.
- Start the built app with Playwright's webServer setting. Never depend on a server I started.
- Find elements by role and visible text, not by CSS classes.
- Keep each test independent.
