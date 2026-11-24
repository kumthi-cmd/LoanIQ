# The Ask the Tape agent

Ask the Tape uses one Claude agent to answer plain-English questions about the loan
tape. The agent decides which data to fetch, LoanIQ's code fetches it, and the agent
explains the result. It never does the math and never sees the whole tape.

## How it works
1. You ask a question.
2. Claude plans the next step and picks a tool.
3. Guardrails check the call: one read-only query, known columns, row and time limits.
4. The tool runs on DuckDB. Claude gets totals and the first 20 rows; the screen gets
   every row.
5. Claude repeats until it can answer. The answer streams back with the SQL behind it.

## Who does what
- **Claude:** plans and explains.
- **LoanIQ's orchestrator:** runs the loop, checks every call, enforces the limits.
- **Tools:** do every calculation: `list_columns`, `query_tape`, `summarize_tape`,
  `lookup_term`, `get_loan`.
- **DuckDB:** the single source of truth.

## Cost and models
Tape questions run on Claude Haiku 5.5, about $0.001 each. Saved queries and
desk-question chips skip the model. A daily cap and a per-visitor limit apply; past
them, built-in rules answer instead. The model can be swapped (Claude, ChatGPT,
Gemini) through one provider interface.

## Why you can trust the numbers
Every number comes from a tool result, and every answer shows its SQL. A set of
golden questions with known answers must pass before a release. All loans are
synthetic.
