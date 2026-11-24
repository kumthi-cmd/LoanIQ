## Business
A trader asks the tape what they would otherwise ask an analyst. Which New York loans
could go into a low loan balance pool? What is the WAC of the FHA loans? Who sells the
loans that are 90 days late or worse? The answer comes back in seconds, with the loans
behind it.

Each answer shows how it was reached. Every tool the agent called appears as a chip.
Click a chip to see the exact SQL that ran. Click a loan ID to see every field of that
loan. **Open in Loan Tape** opens the full grid with the same filter, written as
ordinary column filters you can read and change. If the filter can't be written that
way, for example a list of five delinquency statuses, the button says why.

**Save query** keeps an answer's SQL under a short tag. The last five sit on the
right. One click reruns them on the tape without the AI model, so a question the desk
asks of every tape costs nothing and follows the same rule each time.

When the AI model isn't available, built-in rules answer instead and a small
"Offline" banner says so. That happens when the server has no key or today's limit is
reached. The desk questions and saved queries still work. All loans are synthetic.

## Technical
The screen sends the question to `POST /api/ask` and reads the answer as a stream of
Server-Sent Events: each tool call and its result (with the SQL), any fallback, the
answer, then a summary with the cost. Each result's rows come from
`GET /api/ask/queries/{id}`. The agent's loop, tools and guardrails are described in
`content/agent.md`.

Three more routes serve the screen, and none of them calls a model:
- `GET /api/ask/status` tells the screen whether the model or the built-in rules will
  answer, so the Offline banner shows before anyone asks.
- `GET /api/ask/loans/{id}` runs the agent's own `get_loan` tool for the loan drawer.
- `POST /api/ask/rerun` reruns a saved query's SQL through the same guardrail as the
  model's SQL (one SELECT, known columns, bound values, row cap, timeout).

**Open in Loan Tape** comes from the back end. sqlglot reads the query's WHERE and
ORDER BY and turns simple conditions (`=`, `<>`, `>`, `>=`, `<`, `<=`, `BETWEEN`,
`IN` with two values, `LIKE '%text%'`) into the grid's own filter model. The Loan
Tape reads it from the URL (`/?filter=…&sort=…`). The link is data, never SQL, and
the grid's API checks it again. A grid column holds at most two conditions, so a
longer list can't open.

Saved queries live in your browser's localStorage, so they are yours alone. If
storage is blocked, the screen still works without them. Ctrl K, or the header's
"Ask the tape" box, opens this screen with the question filled in but not sent, so no
model call is made until you press Send.
