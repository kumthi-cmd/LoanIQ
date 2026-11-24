"""Ask the Tape: the agent that answers plain-English questions about the loan tape.

Where it sits:
    loan tape (DuckDB) -> [agent: providers, tools, orchestrator] -> POST /api/ask
    -> the Ask the Tape screen (Step 4b)

BUSINESS: a visitor asks "what is the WAC of the New York loans?"; a model plans
  which data to fetch, LoanIQ's tools fetch and compute it, and the model explains
  the result. The model never does the math and never sees the whole tape.
  The design is content/agent.md.
TECH: config.py (llm.toml), providers/ (one interface, several models: Strategy
  pattern), sql_guard.py (the query_tape guardrails), tools.py, query_store.py,
  budget.py (cost and limits), orchestrator.py (the loop), golden.py (golden
  questions and grading), service.py (wires it all for main.py).
"""
