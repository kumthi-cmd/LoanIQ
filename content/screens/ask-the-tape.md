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

The agent's scope grows with the desk. The strip under the title, **Knows: Tape ✓ ·
Slotting – · BestEx –**, shows which stages it knows. Before Product Slotting has run,
a question about slots gets a plain "not run yet". Once the desk has run it, the agent
answers from the same slots as the Loan Tape: how many loans are deliverable, the UPB
in UMBS, the loans in each LLB tier or with the New York story, and, for one loan,
exactly why it is or is not slotted. Best execution and the later stages join as they
are built.

When the AI model isn't available, built-in rules answer instead and a small
"Offline" banner says so. That happens when the server has no key or today's limit is
reached. The desk questions and saved queries still work. All loans are synthetic.

## Technical
When an answer is about specific loans (one row per loan), its table always shows
the same 12 columns the Loan Tape opens with, in the same order, followed by any
column the agent worked out for the question. The server adds them. It reads the
list from one setting (`backend/app/config/api.toml`) that both screens use, and
fetches the missing fields for exactly those loan IDs in one query with bound
values. The AI model never sees the added columns, so they cost nothing in tokens and
can't change its answer. The SQL shown on screen is still exactly what the agent
ran. Each column is as wide as its widest value, and headers wrap if needed, so all
12 fit across without stretching.

The agent's copy of the tape follows the desk's stages (`backend/app/agent/stages.py`).
When a stage finishes (today, a Product Slotting run), the copy is rebuilt in the
background with that stage's columns as plain, flat columns (`deliverable`, `agency`,
`down_coupon`, `llb_tier`, `story_ny` and so on), so the one-table SQL guard stays as
strict as before, and swapped in; a question already running finishes on the old copy.
The system prompt gains that stage's short section and the tool list its tools
(`explain_slot`, the same card as the Loan Tape's hover). The copy lives in memory with
the tape, so after a server restart the agent knows the tape again until the desk
reruns slotting.

The screen sends the question to `POST /api/ask` and reads the answer as a stream of
Server-Sent Events: each tool call and its result (with the SQL), any fallback, the
answer, then a summary with the cost. Each result's rows come from
`GET /api/ask/queries/{id}`. The agent's loop, tools and guardrails are described in
`content/agent.md`. The gold **Agent** mark beside the title and in the sidebar
opens that same text and a diagram of the loop, without leaving the screen.

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
