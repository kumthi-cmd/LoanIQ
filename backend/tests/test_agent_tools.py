"""Tests for the agent's tools, query store, budget and config.

BUSINESS: the tools are where every number in an answer is computed, so these
  tests check their numbers against the grid's own store (an independent copy of
  the tape): counts, totals, the summary the Loan Tape screen shows, one loan's
  fields, glossary definitions. They also protect the spending rules: the cost
  formula, the daily dollar cap and the per-visitor limit.
TECH: TapeTools over the real read-only tape (tests/agent_fixtures.py). Each tool
  call is a ToolCall, as a model would send it.
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any

import pytest

from app import main
from app.agent.budget import SpendMeter, cost_usd, visitor_key
from app.agent.config import Budget, ModelPrice, load_agent_config, parse_config
from app.agent.providers.base import ToolCall, Usage
from app.agent.query_store import QueryStore, StoredQuery
from app.agent.tape_db import ReadOnlyTape
from app.agent.tools import TOOL_SPECS, TapeTools, column_totals, run_sql, to_csv
from tests.agent_fixtures import (agent_cfg, loan_store, ro_tape, tape_dir,  # noqa: F401
                                  with_limits)


@pytest.fixture()
def tools(ro_tape: ReadOnlyTape, loan_store: main.LoanStore, agent_cfg: Any) -> TapeTools:  # noqa: F811
    """TapeTools as the app builds them, over the seeded tape."""
    glossary = [{"term": "WAC", "definition": "Weighted-average coupon.", "why": "Sets coupons."},
                {"term": "LTV", "definition": "Loan-to-value.", "why": "Equity cushion."}]
    store = QueryStore(agent_cfg.limits.query_store_size, agent_cfg.limits.query_store_ttl_s)
    return TapeTools(ro_tape.con, loan_store.columns, main.load_labels(), glossary,
                     lambda: main.tape_summary(loan_store), store, agent_cfg.limits)


def call(tools: TapeTools, name: str, **args: Any) -> Any:
    """Run one tool call the way the orchestrator does."""
    return tools.run(ToolCall(id="t1", name=name, input=args))


def truth(loan_store: main.LoanStore, sql: str) -> Any:  # noqa: F811
    """An answer from the grid's own in-memory store (test-only constant SQL)."""
    return loan_store.con.execute(sql).fetchone()[0]


# =============================================================================
# Tool specs
# =============================================================================

def test_every_tool_schema_is_strict() -> None:
    """BUSINESS: the model can only send the arguments a tool expects.

    TECH: every property required, nothing extra: the shape Claude's, OpenAI's and
      Gemini's strict modes all accept.
    """
    assert [t.name for t in TOOL_SPECS] == ["list_columns", "query_tape", "summarize_tape",
                                           "lookup_term", "get_loan"]
    for spec in TOOL_SPECS:
        s = spec.input_schema
        assert s["type"] == "object" and s["additionalProperties"] is False
        assert sorted(s["required"]) == sorted(s["properties"])


# =============================================================================
# query_tape
# =============================================================================

def test_query_tape_count_matches_the_tape(tools: TapeTools, loan_store: main.LoanStore) -> None:  # noqa: F811
    """BUSINESS: "how many loans over 125 LTV" is the tape's real count."""
    out = call(tools, "query_tape", title="High LTV", sql="SELECT COUNT(*) AS n FROM loans WHERE ltv > 125")
    assert out.event["status"] == "ok" and not out.result.is_error
    assert out.result.data["rows"][0]["n"] == truth(loan_store, "SELECT COUNT(*) FROM loans WHERE ltv > 125")


def test_query_tape_stores_every_row_but_shows_the_model_twenty(tools: TapeTools) -> None:
    """BUSINESS: the model sees totals and 20 rows; the screen gets all of them.

    TECH: 101 New York loans -> 101 rows stored, 20 CSV rows plus a header for the
      model, and totals over all 101 rows.
    """
    out = call(tools, "query_tape", title="NY", sql="SELECT loan_id, current_upb FROM loans WHERE state = 'NY'")
    stored = tools.store.get(out.event["query_id"])
    assert stored is not None and stored.row_count == out.event["row_count"] > 20
    csv_lines = out.result.content.split("csv:\n")[1].strip().splitlines()
    assert len(csv_lines) == 21 and csv_lines[0] == "loan_id,current_upb"
    total = round(sum(r[1] for r in stored.rows), 2)
    assert f"current_upb sum={total}" in out.result.content


def test_query_tape_caps_at_500_rows_and_reports_the_full_count(tools: TapeTools) -> None:
    """BUSINESS: the screen never gets more than 500 loans at once, and the model is
    told how many matched in total (2,000)."""
    out = call(tools, "query_tape", title="All", sql="SELECT loan_id FROM loans")
    assert out.event["row_count"] == 500 and out.event["truncated"] is True
    assert out.event["total_rows"] == 2000
    assert "capped; 2000 rows match" in out.result.content


def test_query_tape_refusal_is_a_guardrail_failure(tools: TapeTools) -> None:
    """BUSINESS: a refused query goes back to the model with the reason, and counts
    towards moving up to the stronger model."""
    out = call(tools, "query_tape", title="Bad", sql="DELETE FROM loans")
    assert out.rejected and out.result.is_error and out.event["status"] == "rejected"
    assert "Only SELECT" in out.result.content and out.event["sql"] == "DELETE FROM loans"


def test_query_tape_duckdb_error_goes_back_to_the_model(tools: TapeTools) -> None:
    """BUSINESS: a query DuckDB cannot run (comparing a date to a number) is sent
    back with DuckDB's reason, so the model can fix it."""
    out = call(tools, "query_tape", title="Bad", sql="SELECT COUNT(*) FROM loans WHERE orig_date > 5")
    assert out.rejected and "DuckDB refused" in out.result.content


def test_slow_queries_are_interrupted(ro_tape: ReadOnlyTape) -> None:  # noqa: F811
    """BUSINESS: one query cannot hold the server; it is stopped after its time limit.

    TECH: a cross join of the tape with itself three times (8 billion rows) cannot
      finish in 50 ms; DuckDB is interrupted and the tool reports it.
    """
    from app.agent.tools import ToolFailure
    started = time.monotonic()
    with pytest.raises(ToolFailure, match="longer than 50 ms"):
        run_sql(ro_tape.con, "SELECT COUNT(*) FROM loans a, loans b, loans c", [], 50)
    assert time.monotonic() - started < 5


def test_query_tape_is_fast_on_the_tape(tools: TapeTools, agent_cfg: Any) -> None:  # noqa: F811
    """BUSINESS: the agent's tools add little to the visitor's wait.

    TECH: guard + run + store for a grouped weighted average well under the query
      timeout (llm.toml query_timeout_ms).
    """
    started = time.monotonic()
    out = call(tools, "query_tape", title="WAC by state",
               sql="SELECT state, SUM(note_rate * current_upb) / SUM(current_upb) AS wac "
                   "FROM loans GROUP BY state ORDER BY wac DESC")
    elapsed_ms = (time.monotonic() - started) * 1000
    assert out.event["status"] == "ok"
    assert elapsed_ms < agent_cfg.limits.query_timeout_ms / 4


# =============================================================================
# The other tools
# =============================================================================

def test_summarize_tape_matches_the_screen(tools: TapeTools, loan_store: main.LoanStore) -> None:  # noqa: F811
    """BUSINESS: the agent quotes the same headline numbers as the Loan Tape screen's
    tiles, because it calls the same function."""
    out = call(tools, "summarize_tape")
    screen = main.fetch_summary(loan_store)
    assert out.result.data["wac"] == screen.wac and out.result.data["loan_count"] == screen.loan_count
    assert "program_mix: Conventional" in out.result.content
    assert "SUM(note_rate * current_upb)" in out.event["sql"]


def test_list_columns_lists_every_tape_column(tools: TapeTools, loan_store: main.LoanStore) -> None:  # noqa: F811
    """BUSINESS: the model's map of the tape, with readable labels and units."""
    out = call(tools, "list_columns")
    assert out.result.data["columns"] == list(loan_store.columns)
    assert "current_upb DECIMAL(14,2) number | Current UPB ($)" in out.result.content


def test_get_loan_returns_one_loans_fields(tools: TapeTools, loan_store: main.LoanStore) -> None:  # noqa: F811
    """BUSINESS: drilling into one loan shows the same fields the grid does."""
    loan_id = truth(loan_store, "SELECT loan_id FROM loans ORDER BY loan_id LIMIT 1")
    out = call(tools, "get_loan", loan_id=loan_id.lower())
    assert out.result.data["loan"]["loan_id"] == loan_id
    assert f"fico: {out.result.data['loan']['fico']}" in out.result.content


@pytest.mark.parametrize("loan_id, rejected", [("LN99999999", False), ("1; DROP", True)])
def test_get_loan_unknown_or_malformed(tools: TapeTools, loan_id: str, rejected: bool) -> None:
    """BUSINESS: an unknown loan is an honest "not found"; a malformed id is refused."""
    out = call(tools, "get_loan", loan_id=loan_id)
    assert out.result.is_error and out.rejected is rejected


def test_lookup_term_exact_near_and_missing(tools: TapeTools) -> None:
    """BUSINESS: definitions come from the glossary, not the model's memory."""
    assert "Weighted-average coupon" in call(tools, "lookup_term", term="wac").result.content
    assert "Loan-to-value" in call(tools, "lookup_term", term="the LTV").result.content
    missing = call(tools, "lookup_term", term="zebra")
    assert missing.result.is_error and not missing.rejected and "WAC, LTV" in missing.result.content


@pytest.mark.parametrize("name, args, reason", [
    ("drop_tape", {}, "Unknown tool"),
    ("query_tape", {"sql": "SELECT 1"}, "takes exactly"),
    ("get_loan", {"loan_id": 12345678}, "must be text"),
])
def test_bad_calls_are_rejected(tools: TapeTools, name: str, args: dict, reason: str) -> None:
    """BUSINESS: a call to a tool that does not exist, or with the wrong arguments,
    is refused and counted, never half-run."""
    out = tools.run(ToolCall("t1", name, args))
    assert out.rejected and reason in out.result.content


def test_csv_and_totals_helpers() -> None:
    """TECH: NULL is an empty cell; totals skip text and booleans and stay exact."""
    assert to_csv(["a", "b"], [[1, None]]) == "a,b\n1,\n"
    totals = column_totals(["upb", "flag", "name"], [[0.1, True, "x"], [0.2, False, "y"]])
    assert totals == {"upb": {"sum": 0.3, "min": 0.1, "max": 0.2}}


# =============================================================================
# Query store
# =============================================================================

def stored(qid: str) -> StoredQuery:
    """A minimal stored result."""
    return StoredQuery(query_id=qid, title="t", sql="SELECT 1", columns=["a"], rows=[[1]],
                       row_count=1, total_rows=1, truncated=False)


def test_query_store_drops_the_oldest_and_expires() -> None:
    """BUSINESS: results stay available for the screen for an hour, and memory stays
    bounded. TECH: a fake clock moves time forward."""
    now = [0.0]
    store = QueryStore(max_size=2, ttl_s=60, clock=lambda: now[0])
    for qid in ("q1", "q2", "q3"):
        store.put(stored(qid))
    assert store.get("q1") is None and store.get("q3") is not None
    now[0] = 61
    assert store.get("q2") is None
    assert QueryStore.new_id() != QueryStore.new_id()


# =============================================================================
# Budget and cost
# =============================================================================

def test_cost_formula_in_dollars() -> None:
    """BUSINESS: cost = tokens x price per million, for each kind of token.

    TECH: 1,000 input at $0.10, 200 output at $0.50, 3,000 cache reads at $0.01 and
      500 cache writes at $0.125 per million = $0.0001 + $0.0001 + $0.00003 +
      $0.0000625 = $0.0002925, exactly.
    """
    price = ModelPrice(Decimal("0.10"), Decimal("0.50"), Decimal("0.01"), Decimal("0.125"))
    assert cost_usd(Usage(1000, 200, 3000, 500), price) == Decimal("0.0002925")


def test_daily_cap_and_visitor_limit() -> None:
    """BUSINESS: past the day's dollar cap, or one visitor's question count, built-in
    rules answer. A new UTC day starts fresh."""
    day = ["2026-11-23"]
    meter = SpendMeter(Budget(Decimal("0.01"), 2, False), today=lambda: day[0])
    assert meter.check("a") is None
    meter.record("a", Decimal("0.001"))
    meter.record("a", Decimal("0.001"))
    assert meter.check("a") == "visitor_limit" and meter.check("b") is None
    meter.record("b", Decimal("0.01"))
    assert meter.check("c") == "daily_budget"
    day[0] = "2026-11-24"
    assert meter.check("a") is None and meter.spent == 0


def test_visitor_key_uses_the_proxy_address_and_hides_the_ip() -> None:
    """BUSINESS: a visitor is counted without their address being stored, and cannot
    dodge the limit by typing a fake X-Forwarded-For (Render appends the real one).
    """
    real = visitor_key("1.2.3.4, 9.9.9.9", "10.0.0.1", True, "salt")
    assert real == visitor_key("5.6.7.8, 9.9.9.9", "10.0.0.1", True, "salt")
    assert real != visitor_key(None, "10.0.0.1", True, "salt")
    assert "9.9.9.9" not in real and len(real) == 16
    assert visitor_key("1.2.3.4", "10.0.0.1", False, "s") == visitor_key(None, "10.0.0.1", False, "s")


# =============================================================================
# Config
# =============================================================================

def test_shipped_config_routes_haiku_then_sonnet_then_offline() -> None:
    """BUSINESS: the step's model choice: Claude Haiku 5.5 for tape questions, Claude
    Sonnet 5.5 after two refused calls, built-in rules as the fallback."""
    route = load_agent_config().tasks["tape_query"]
    assert (route.provider, route.model, route.escalation_model, route.escalate_after,
            route.fallback_provider) == ("anthropic", "claude-haiku-5-5", "claude-sonnet-5-5", 2, "offline")


def test_shipped_limits() -> None:
    """BUSINESS: 5 rounds, 800 output tokens, 20 seconds, 500 rows, 20 rows to the model."""
    lim = load_agent_config().limits
    assert (lim.max_rounds, lim.max_output_tokens, lim.question_timeout_s, lim.max_rows,
            lim.rows_to_model) == (5, 800, 20, 500, 20)


def raw_config(**overrides: Any) -> dict[str, Any]:
    """A minimal valid llm.toml dict, with some parts replaced."""
    raw: dict[str, Any] = {
        "tasks": {"tape_query": {"provider": "anthropic", "model": "m1"}},
        "models": {"m1": {"input": 1, "output": 1, "cache_read": 0, "cache_write": 1}},
        "limits": {k: 1 for k in ("max_rounds", "max_output_tokens", "question_timeout_s",
                                  "max_question_chars", "max_rows", "query_timeout_ms",
                                  "max_sql_chars", "rows_to_model", "query_store_size",
                                  "query_store_ttl_s")},
        "budget": {"daily_cap_usd": 1, "questions_per_visitor_per_day": 1},
    }
    raw.update(overrides)
    return raw


@pytest.mark.parametrize("overrides, message", [
    ({"tasks": {"t": {"provider": "skynet", "model": "m1"}}}, "unknown provider"),
    ({"models": {}}, "has no \\[models\\] prices"),
    ({"models": {"m1": {"input": -1, "output": 1, "cache_read": 0, "cache_write": 1}}}, "negative"),
    ({"offline": {"rule": [{"kind": "magic", "id": "x", "keywords": ["a"]}]}}, "kind must be"),
    ({"offline": {"rule": [{"kind": "summary", "id": "x", "keywords": []}]}}, "at least one keyword"),
])
def test_bad_config_stops_start_up(overrides: dict, message: str) -> None:
    """BUSINESS: a typo in llm.toml fails loudly at start-up, never on a visitor's
    question, and a model can never run without a price (it would count as free)."""
    with pytest.raises(ValueError, match=message):
        parse_config(raw_config(**overrides))


def test_price_lookup_names_a_missing_model(agent_cfg: Any) -> None:  # noqa: F811
    """TECH: asking for an unpriced model says which one."""
    with pytest.raises(KeyError, match="gpt-x"):
        agent_cfg.price("gpt-x")


def test_with_limits_helper(agent_cfg: Any) -> None:  # noqa: F811
    """TECH: the test helper changes only what it is told to."""
    changed = with_limits(agent_cfg, max_rounds=2)
    assert changed.limits.max_rounds == 2 and changed.limits.max_rows == agent_cfg.limits.max_rows
