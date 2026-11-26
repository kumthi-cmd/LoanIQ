"""The orchestrator: LoanIQ's agent loop around the model.

Where it sits:
    POST /api/ask -> [Orchestrator.ask] -> provider.chat <-> TapeTools.run
    -> events (tool calls, results, answer, done) streamed to the screen

BUSINESS:
    "LoanIQ's orchestrator runs the loop, checks every call, enforces the limits"
    (content/agent.md). One question goes:
      1. budget and availability checks: if the model may not answer, built-in
         rules do, and the screen says why
      2. the model plans and asks for a tool; LoanIQ checks and runs it
      3. the result goes back; repeat until the model answers, at most 5 rounds
         and 20 seconds (llm.toml [limits])
      4. a refused call goes back to the model as the tool result, so it can fix
         its query; after 2 refusals the question moves to the stronger model
      5. if the model fails, times out, declines or runs out of rounds, built-in
         rules answer instead
      6. tokens and dollars are added up, logged and counted against the budget

TECH:
    - ask() is a generator of Event objects. The SSE route forwards each one as it
      happens; tests just collect them in a list. `yield from` passes events up
      from loop(), and loop()'s return value is the answer text.
    - The loop is written here rather than with the SDK's tool runner because
      LoanIQ must see and check every call, count refusals, switch model mid-
      question and stop on its own clock; and the same loop drives every provider.
    - The system prompt is app/agent/system_prompt.md plus a section per finished
      stage (agent/stages.py, Step 5c), and the tool list is the tools of those
      stages. Both are fixed for the whole question, from the stages known when it
      starts. The prompt holds no date or id and changes only when a stage
      finishes, so it is byte-for-byte the same between stage changes and prompt
      caching works.
    - One JSON log line per question: provider, models, rounds, tokens, cost,
      fallback reason, time. The question's text and the visitor are not logged.
      When a model call fails, one more line (log_provider_error, Step 4b) gives
      the provider's status and its own error message, never the key or question.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Generator, Iterator
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.agent.budget import SpendMeter, cost_usd
from app.agent.config import AgentConfig, TaskRoute
from app.agent.providers.base import (AssistantTurn, ChatOptions, LLMProvider, Message,
                                      ProviderError, ToolResults, Usage, UserText)
from app.agent.providers.offline_provider import OfflineProvider
from app.agent import stages as stage_info
from app.agent.providers.base import ToolSpec
from app.agent.tools import TapeTools

SYSTEM_PROMPT_PATH = stage_info.BASE_PROMPT_PATH
TASK = "tape_query"
OFFLINE_MODEL = "offline"
# TECH: provider error reasons that have their own notice; anything else is "error".
NOTICE_REASONS = {"unavailable", "daily_budget", "visitor_limit", "timeout", "refusal",
                  "round_limit", "desk_question"}

log = logging.getLogger("loaniq.ask")


@dataclass(frozen=True)
class Event:
    """One step the screen sees. TECH: type is the SSE event name; data is JSON-ready."""
    type: str
    data: dict[str, Any]


class RoundLimit(Exception):
    """The model used every round without answering."""


@dataclass
class Run:
    """Running totals for one question.

    TECH: usage is per model id, because each model has its own prices.
      model_used is True once a paid provider was called, so the question counts
      against the visitor's limit and the daily budget even if it then fell back.
    """
    started: float
    rounds: int = 0
    usage: dict[str, Usage] = field(default_factory=dict)
    query_ids: list[str] = field(default_factory=list)
    model_used: bool = False
    model: str | None = None

    def add(self, model: str, usage: Usage) -> None:
        """Add one call's tokens under its model."""
        self.usage.setdefault(model, Usage()).add(usage)

    def total(self) -> Usage:
        """All tokens across models."""
        out = Usage()
        for u in self.usage.values():
            out.add(u)
        return out


class Orchestrator:
    """Runs questions. TECH: one instance per app; ask() is safe to call concurrently."""

    def __init__(self, cfg: AgentConfig, providers: dict[str, LLMProvider],
                 offline: OfflineProvider, tools: TapeTools, meter: SpendMeter,
                 notices: dict[str, str], system_prompt: str | None = None,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.cfg, self.providers, self.offline, self.tools = cfg, providers, offline, tools
        self.meter, self.notices, self.clock = meter, notices, clock
        # TECH: a test may pin the whole prompt; otherwise it follows the stages.
        self.fixed_system = system_prompt

    def context(self) -> tuple[str, list[ToolSpec]]:
        """The system prompt and tool list for a question starting now.

        BUSINESS: the agent knows the stages the desk has finished, and is offered
          their tools, and no others.
        """
        done = self.tools.stages
        system = self.fixed_system or stage_info.system_prompt(done)
        return system, self.tools.specs(done)

    @property
    def system(self) -> str:
        """TECH: the system prompt a question starting now would get."""
        return self.context()[0]

    # ------------------------------------------------------------------ the question

    def ask(self, question: str, visitor: str, desk_question: str | None = None) -> Iterator[Event]:
        """Answer one question, yielding events; the last one is "done".

        BUSINESS: the model answers when it may; otherwise built-in rules do, with
          a notice saying why.
        """
        run = Run(started=self.clock())
        route = self.cfg.tasks[TASK]
        provider = self.providers.get(route.provider, self.offline)
        reason = self.blocked_reason(provider, visitor, desk_question)
        answer, served_by, model = "", self.offline.name, OFFLINE_MODEL
        if reason is None:
            try:
                answer = yield from self.loop(provider, route, question, run)
                served_by, model = provider.name, self.last_model(run, route)
            except (ProviderError, RoundLimit) as exc:
                reason = exc.reason if isinstance(exc, ProviderError) else "round_limit"
                if isinstance(exc, ProviderError):
                    self.log_provider_error(provider, run, exc, question)
                yield Event("fallback", {"reason": reason, "notice": self.notice(reason)})
        if reason is not None:
            rules = self.offline.pinned(desk_question) if desk_question else self.offline
            answer = yield from self.loop(rules, None, question, run)
        cost = self.cost(run)
        if run.model_used:
            self.meter.record(visitor, cost)
        yield Event("answer", {"text": answer, "provider": served_by, "model": model,
                               "notice": self.notice(reason) if reason else None})
        yield Event("done", self.summary(run, served_by, reason, cost))

    def blocked_reason(self, provider: LLMProvider, visitor: str,
                       desk_question: str | None) -> str | None:
        """Why the model may not answer, or None.

        BUSINESS: desk-question chips always skip the model; then a switched-off
          model; then the daily budget and the visitor's limit (budget.py).
        """
        if desk_question:
            if desk_question not in self.offline.questions:
                raise KeyError(desk_question)
            return "desk_question"
        if provider is self.offline or not provider.available():
            return "unavailable"
        return self.meter.check(visitor)

    def status(self, visitor: str) -> str | None:
        """Why built-in rules would answer this visitor's next typed question, or None.

        BUSINESS: lets the screen show the Offline banner before anyone asks.
        TECH: the same checks as ask(), without calling anything or counting.
        """
        route = self.cfg.tasks[TASK]
        return self.blocked_reason(self.providers.get(route.provider, self.offline), visitor, None)

    # ------------------------------------------------------------------ the loop

    def loop(self, provider: LLMProvider, route: TaskRoute | None, question: str,
             run: Run) -> Generator[Event, None, str]:
        """Model turn -> tool calls -> results, until an answer. Returns the answer text.

        TECH: route is None for the offline rules (no model, no escalation, no clock:
          they answer in milliseconds). Raises ProviderError on timeout or a failed
          call, RoundLimit after max_rounds turns without an answer.
        """
        lim = self.cfg.limits
        system, specs = self.context()
        messages: list[Message] = [UserText(question)]
        model = route.model if route else OFFLINE_MODEL
        failures = 0
        for _ in range(lim.max_rounds):
            run.model = model  # TECH: the model being called, for the error log
            turn = provider.chat(system, messages, specs, model,
                                 lim.max_output_tokens, self.options(route, model, run))
            run.rounds += 1
            if route:
                run.model_used = True
                run.add(model, turn.usage)
            messages.append(AssistantTurn(turn))
            if not turn.tool_calls:
                if not turn.text.strip():
                    raise ProviderError("empty", f"{provider.name} returned no answer "
                                                 f"(stop reason {turn.stop_reason})")
                return turn.text
            failures += yield from self.run_tools(turn.tool_calls, messages, run)
            if route and self.should_escalate(route, model, failures):
                model = route.escalation_model
                yield Event("escalated", {"model": model, "guardrail_failures": failures})
        raise RoundLimit()

    def run_tools(self, calls: list[Any], messages: list[Message],
                  run: Run) -> Generator[Event, None, int]:
        """Run every call of one turn; append all results as one message.

        TECH: returns how many calls were rejected (guardrail failures).
        """
        results, rejected = [], 0
        for call in calls:
            yield Event("tool_call", {"id": call.id, "name": call.name, "input": call.input})
            outcome = self.tools.run(call)
            yield Event("tool_result", outcome.event)
            results.append(outcome.result)
            rejected += int(outcome.rejected)
            if "query_id" in outcome.event:
                run.query_ids.append(outcome.event["query_id"])
        messages.append(ToolResults(tuple(results)))
        return rejected

    def options(self, route: TaskRoute | None, model: str, run: Run) -> ChatOptions:
        """Time left for this question, and the model's effort setting.

        TECH: raises ProviderError("timeout") once the question's time is used up,
          before another call is started.
        """
        if route is None:
            return ChatOptions()
        left = self.cfg.limits.question_timeout_s - (self.clock() - run.started)
        if left <= 0:
            raise ProviderError("timeout", "The question used its time limit")
        effort = self.cfg.models[model].effort if model in self.cfg.models else None
        return ChatOptions(timeout_s=left, effort=effort)

    @staticmethod
    def should_escalate(route: TaskRoute, model: str, failures: int) -> bool:
        """BUSINESS: after N refused calls, move up to the stronger model, once."""
        return (route.escalate_after > 0 and failures >= route.escalate_after
                and model != route.escalation_model)

    @staticmethod
    def last_model(run: Run, route: TaskRoute) -> str:
        """The model that wrote the answer: the escalation model if it was used."""
        return route.escalation_model if route.escalation_model in run.usage else route.model

    # ------------------------------------------------------------------ cost and log

    def cost(self, run: Run) -> Decimal:
        """Dollars for every model call in the question (budget.cost_usd per model)."""
        return sum((cost_usd(u, self.cfg.price(m)) for m, u in run.usage.items()
                    if m in self.cfg.models), Decimal(0))

    @staticmethod
    def log_provider_error(provider: LLMProvider, run: Run, exc: ProviderError, question: str) -> None:
        """One warning log line saying why a model call failed.

        BUSINESS: when Ask the Tape falls back to built-in rules, the operator
          reading Render's logs sees the provider's own words ("credit balance is
          too low", "model not found") and its HTTP status, not just "http_400".
        TECH: provider, model, reason, status and the provider's message, which
          base.sdk_detail has already cut to length and cleared of API keys. The
          visitor's question is never logged: if the provider echoed it back, it is
          replaced with "[question]" here.
        """
        detail = exc.detail or str(exc)
        if question.strip():
            detail = detail.replace(question.strip(), "[question]")
        log.warning(json.dumps({"event": "provider_error", "provider": provider.name,
                                "model": run.model, "reason": exc.reason,
                                "status": exc.status, "message": detail}))

    def notice(self, reason: str) -> str:
        """The visitor-facing notice for a fallback reason (content/ask-the-tape.json)."""
        return self.notices[reason if reason in NOTICE_REASONS else "error"]

    def summary(self, run: Run, served_by: str, reason: str | None, cost: Decimal) -> dict[str, Any]:
        """The "done" event and the log line.

        TECH: cost_usd as a string with 6 decimals, so JSON never rounds it.
        """
        data = {"provider": served_by, "models": list(run.usage), "rounds": run.rounds,
                "usage": run.total().as_dict(), "cost_usd": f"{cost:.6f}",
                "fallback_reason": reason, "query_ids": run.query_ids,
                "elapsed_ms": round((self.clock() - run.started) * 1000)}
        log.info(json.dumps({"event": "ask", **{k: v for k, v in data.items() if k != "query_ids"},
                             "queries": len(run.query_ids)}))
        return data
