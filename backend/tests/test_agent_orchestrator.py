"""Tests for the orchestrator (app/agent/orchestrator.py): the agent loop and its limits.

BUSINESS: these tests protect the rules around the model: a refused tool call goes
  back to the model to fix; two refusals move the question to the stronger model;
  no question runs past 5 rounds or 20 seconds; any failure, refusal, switched-off
  model or spent budget hands over to built-in rules, which say why; desk-question
  chips never touch the model; every question's tokens and dollars are counted.
TECH: a full AskService over the seeded tape with a FakeProvider registered as
  "anthropic" (tests/agent_fixtures.py), so the real tools, guardrails and budget
  run, and only the model is scripted. Time is faked by replacing the
  orchestrator's clock.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest

from app.agent.budget import cost_usd
from app.agent.providers.anthropic_provider import AnthropicProvider
from app.agent.providers.base import ChatTurn, Message, ProviderError, ToolResults, Usage
from app.agent.providers.fake_provider import FakeProvider, text_turn, tool_turn
from app.agent.service import AskService
from tests.agent_fixtures import (agent_cfg, all_of, events_of, loan_store, make_service,  # noqa: F401
                                  one, tape_dir, with_budget, with_limits)

GOOD_SQL = {"title": "High LTV", "sql": "SELECT COUNT(*) AS n FROM loans WHERE ltv > 125"}
BAD_SQL = {"title": "Bad", "sql": "SELECT purpose FROM loans"}
QUESTION = "How many loans have an LTV over 125?"


def fake_service(make_service: Callable[..., AskService], steps: list, cfg: Any = None) -> tuple[AskService, FakeProvider]:  # noqa: F811
    """A service whose "anthropic" provider is a FakeProvider with these steps."""
    fake = FakeProvider(steps)
    return make_service(providers={"anthropic": fake}, cfg=cfg), fake


# =============================================================================
# The happy path
# =============================================================================

def test_tool_call_then_answer(make_service: Callable[..., AskService], agent_cfg: Any) -> None:  # noqa: F811
    """BUSINESS: the model asks for a query, LoanIQ runs it, the model answers. The
    screen sees each step, and the question is priced at Claude Haiku 5.5's rates.
    """
    service, fake = fake_service(make_service, [tool_turn(("query_tape", GOOD_SQL)), text_turn("20 loans.")])
    events = events_of(service, QUESTION)
    assert [e.type for e in events] == ["tool_call", "tool_result", "answer", "done"]
    result = one(events, "tool_result")
    assert result["status"] == "ok" and "ltv > 125" in result["sql"]
    answer, done = one(events, "answer"), one(events, "done")
    assert answer == {"text": "20 loans.", "provider": "fake", "model": "claude-haiku-5-5", "notice": None}
    expected = cost_usd(Usage(250, 60), agent_cfg.price("claude-haiku-5-5"))
    assert done["cost_usd"] == f"{expected:.6f}" and done["fallback_reason"] is None
    assert done["query_ids"] == [result["query_id"]] and done["rounds"] == 2
    assert service.meter.spent == expected and service.meter.questions == {"v1": 1}


def test_the_model_gets_the_limits_and_the_cached_system_prompt(make_service: Callable[..., AskService]) -> None:  # noqa: F811
    """BUSINESS: 800 output tokens, low effort, the remaining time, and the same
    rules every call (so they are cached).

    TECH: the system prompt is system_prompt.md, identical on both rounds.
    """
    service, fake = fake_service(make_service, [tool_turn(("summarize_tape", {})), text_turn("ok")])
    events_of(service, "Summarize the tape")
    first, second = fake.calls
    assert first.model == "claude-haiku-5-5" and first.max_tokens == 800
    assert first.options.effort == "low" and 0 < first.options.timeout_s <= 20
    assert first.system == second.system and "Ask the Tape" in first.system
    assert [t.name for t in first.tools] == ["list_columns", "query_tape", "summarize_tape",
                                            "lookup_term", "get_loan"]


def test_parallel_tool_calls_return_in_one_message(make_service: Callable[..., AskService]) -> None:  # noqa: F811
    """TECH: every result of one turn goes back together, in call order."""
    service, fake = fake_service(make_service, [
        tool_turn(("summarize_tape", {}), ("lookup_term", {"term": "WAC"})), text_turn("ok")])
    events_of(service, "Summarize and define WAC")
    sent = fake.calls[1].messages[-1]
    assert isinstance(sent, ToolResults) and [r.name for r in sent.results] == ["summarize_tape", "lookup_term"]


# =============================================================================
# Guardrail failures and escalation
# =============================================================================

def test_rejected_call_goes_back_to_the_model(make_service: Callable[..., AskService]) -> None:  # noqa: F811
    """BUSINESS: a refused query is not the end: the model reads why and fixes it."""
    service, fake = fake_service(make_service, [tool_turn(("query_tape", BAD_SQL)),
                                                tool_turn(("query_tape", GOOD_SQL)), text_turn("20.")])
    events = events_of(service, QUESTION)
    statuses = [e["status"] for e in all_of(events, "tool_result")]
    assert statuses == ["rejected", "ok"]
    returned = fake.calls[1].messages[-1].results[0]
    assert returned.is_error and "Unknown column 'purpose'" in returned.content
    assert not all_of(events, "escalated"), "one failure must not escalate"


def test_two_guardrail_failures_escalate_to_sonnet(make_service: Callable[..., AskService], agent_cfg: Any) -> None:  # noqa: F811
    """BUSINESS: after two refused calls the rest of the question runs on Claude
    Sonnet 5.5, and each model's tokens are priced at its own rates."""
    service, fake = fake_service(make_service, [
        tool_turn(("query_tape", BAD_SQL), ("query_tape", BAD_SQL)),
        tool_turn(("query_tape", GOOD_SQL)), text_turn("20 loans.")])
    events = events_of(service, QUESTION)
    assert one(events, "escalated") == {"model": "claude-sonnet-5-5", "guardrail_failures": 2}
    assert [c.model for c in fake.calls] == ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-sonnet-5-5"]
    assert one(events, "answer")["model"] == "claude-sonnet-5-5"
    done = one(events, "done")
    assert done["models"] == ["claude-haiku-5-5", "claude-sonnet-5-5"]
    expected = (cost_usd(Usage(100, 20), agent_cfg.price("claude-haiku-5-5"))
                + cost_usd(Usage(250, 60), agent_cfg.price("claude-sonnet-5-5")))
    assert done["cost_usd"] == f"{expected:.6f}"


# =============================================================================
# Limits and fallbacks: built-in rules answer, and say why
# =============================================================================

def test_round_limit_falls_back_to_built_in_rules(make_service: Callable[..., AskService]) -> None:  # noqa: F811
    """BUSINESS: a model that keeps calling tools is stopped after 5 rounds; built-in
    rules answer the LTV question instead, and the question still counts."""
    service, fake = fake_service(make_service, [tool_turn(("summarize_tape", {}))] * 6)
    events = events_of(service, QUESTION)
    assert len(fake.calls) == 5
    assert one(events, "fallback")["reason"] == "round_limit"
    answer = one(events, "answer")
    assert answer["provider"] == "offline" and answer["text"].startswith("LTV over 125: 20 loans")
    assert "more steps" in answer["notice"] and service.meter.questions == {"v1": 1}


def test_question_time_limit(make_service: Callable[..., AskService]) -> None:  # noqa: F811
    """BUSINESS: after 20 seconds no new model call starts; built-in rules answer.

    TECH: the first step moves the fake clock 21 s forward.
    """
    now = [100.0]

    def slow(_: list[Message]) -> ChatTurn:
        now[0] += 21
        return tool_turn(("summarize_tape", {}))
    service, fake = fake_service(make_service, [slow, text_turn("never")])
    service.orchestrator.clock = lambda: now[0]
    events = events_of(service, QUESTION)
    assert len(fake.calls) == 1 and one(events, "fallback")["reason"] == "timeout"
    assert one(events, "answer")["notice"].endswith("took too long.")


@pytest.mark.parametrize("error, notice", [
    (ProviderError("refusal", "declined"), "declined this question"),
    (ProviderError("http_500", "server error"), "could not be reached"),
    (ProviderError("timeout", "slow"), "took too long"),
])
def test_provider_failures_fall_back(make_service: Callable[..., AskService], error: ProviderError,
                                     notice: str) -> None:  # noqa: F811
    """BUSINESS: whatever goes wrong with the model, the visitor still gets an answer
    from the tape, with an honest notice."""
    service, _ = fake_service(make_service, [error])
    events = events_of(service, "Give me a summary of the tape")
    answer = one(events, "answer")
    assert answer["provider"] == "offline" and notice in answer["notice"]
    assert "2,000 loans" in answer["text"]


def test_empty_answer_falls_back(make_service: Callable[..., AskService]) -> None:  # noqa: F811
    """BUSINESS: a blank reply is never shown as an answer."""
    service, _ = fake_service(make_service, [ChatTurn("  ", [], Usage(10, 0), "max_tokens")])
    assert one(events_of(service, QUESTION), "fallback")["reason"] == "empty"


def test_switched_off_model_is_never_called(make_service: Callable[..., AskService],
                                            monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    """BUSINESS: with no API key on the server, built-in rules answer and nothing is
    counted against the budget."""
    monkeypatch.delenv("LOANIQ_NO_SUCH_KEY", raising=False)
    service = make_service(providers={"anthropic": AnthropicProvider("LOANIQ_NO_SUCH_KEY")})
    events = events_of(service, QUESTION)
    assert one(events, "done")["fallback_reason"] == "unavailable"
    assert not all_of(events, "fallback") and service.meter.questions == {}


def test_daily_budget_cap(make_service: Callable[..., AskService], agent_cfg: Any) -> None:  # noqa: F811
    """BUSINESS: once the day's dollars are spent, the model is not called."""
    cfg = with_budget(agent_cfg, daily_cap_usd=Decimal(0))
    service, fake = fake_service(make_service, [text_turn("never")], cfg)
    answer = one(events_of(service, QUESTION), "answer")
    assert fake.calls == [] and "budget" in answer["notice"]


def test_visitor_limit(make_service: Callable[..., AskService], agent_cfg: Any) -> None:  # noqa: F811
    """BUSINESS: one visitor's daily questions are capped; other visitors are not."""
    cfg = with_budget(agent_cfg, questions_per_visitor_per_day=1)
    service, fake = fake_service(make_service, [text_turn("one"), text_turn("two")], cfg)
    assert one(events_of(service, "q1", "alice"), "answer")["text"] == "one"
    assert one(events_of(service, QUESTION, "alice"), "done")["fallback_reason"] == "visitor_limit"
    assert one(events_of(service, "q3", "bob"), "answer")["text"] == "two"


def test_desk_question_skips_the_model(make_service: Callable[..., AskService]) -> None:  # noqa: F811
    """BUSINESS: a desk-question chip costs nothing and never counts as a question,
    but still shows its SQL and returns its loans."""
    service, fake = fake_service(make_service, [text_turn("never")])
    events = events_of(service, "", desk_question="new_york")
    done = one(events, "done")
    assert fake.calls == [] and done["cost_usd"] == "0.000000" and len(done["query_ids"]) == 2
    assert one(events, "answer")["text"].startswith("New York: ")
    assert all("state = 'NY'" in r["sql"] for r in all_of(events, "tool_result"))
    assert service.meter.questions == {}


def test_unknown_desk_question_is_an_error(make_service: Callable[..., AskService]) -> None:  # noqa: F811
    """TECH: the API checks ids first (HTTP 400); the orchestrator refuses too."""
    service, _ = fake_service(make_service, [])
    with pytest.raises(KeyError):
        events_of(service, "", desk_question="no_such_chip")


def test_one_log_line_per_question_without_the_question(make_service: Callable[..., AskService],
                                                        caplog: pytest.LogCaptureFixture) -> None:  # noqa: F811
    """BUSINESS: cost and tokens per question are logged; what the visitor typed is not."""
    service, _ = fake_service(make_service, [text_turn("ok")])
    with caplog.at_level(logging.INFO, logger="loaniq.ask"):
        events_of(service, "My secret question about NY")
    lines = [json.loads(r.message) for r in caplog.records if r.name == "loaniq.ask"]
    assert len(lines) == 1 and lines[0]["event"] == "ask" and lines[0]["usage"]["input_tokens"] == 150
    assert "secret" not in caplog.text and "cost_usd" in lines[0]
