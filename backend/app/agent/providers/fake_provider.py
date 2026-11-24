"""The Fake provider: scripted replies, for tests and for running golden questions in CI.

Where it sits:
    tests / golden questions -> orchestrator -> [FakeProvider.chat] (no network)

BUSINESS: lets every test of the loop, the guardrails and the API run in CI in
  milliseconds, for free, with the same answer every time.
TECH: a script is a list of steps, used in order, one per chat() call. A step is a
  ChatTurn (returned as is), a ProviderError (raised, to test fallbacks), or a
  function of the messages so far that returns a ChatTurn (to write an answer from
  real tool results). Every call is recorded in .calls for assertions.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Union

from app.agent.providers.base import (ChatOptions, ChatTurn, LLMProvider, Message, ProviderError,
                                      ToolCall, ToolSpec, Usage)

Step = Union[ChatTurn, ProviderError, Callable[[list[Message]], ChatTurn]]


@dataclass(frozen=True)
class RecordedCall:
    """One chat() call as the fake saw it. TECH: messages is a copy of the history."""
    system: str
    messages: list[Message]
    tools: list[ToolSpec]
    model: str
    max_tokens: int
    options: ChatOptions


class FakeProvider(LLMProvider):
    """Replays a script. TECH: running past the end raises ProviderError("script_ended")."""

    name = "fake"

    def __init__(self, steps: Sequence[Step] = ()) -> None:
        self.steps = list(steps)
        self.calls: list[RecordedCall] = []

    def chat(self, system: str, messages: list[Message], tools: list[ToolSpec],
             model: str, max_tokens: int, options: ChatOptions = ChatOptions()) -> ChatTurn:
        """Return (or raise) the next scripted step."""
        self.calls.append(RecordedCall(system, list(messages), list(tools), model, max_tokens, options))
        if len(self.calls) > len(self.steps):
            raise ProviderError("script_ended", "The fake provider's script has no more steps")
        step = self.steps[len(self.calls) - 1]
        if isinstance(step, ProviderError):
            raise step
        return step(list(messages)) if callable(step) else step


def tool_turn(*calls: tuple[str, dict], usage: Usage | None = None) -> ChatTurn:
    """A scripted reply that calls tools: tool_turn(("query_tape", {...}), ...).

    TECH: call ids are c1, c2, ... within the turn.
    """
    tool_calls = [ToolCall(id=f"c{i + 1}", name=name, input=args) for i, (name, args) in enumerate(calls)]
    return ChatTurn(text="", tool_calls=tool_calls, usage=usage or Usage(100, 20), stop_reason="tool_use")


def text_turn(text: str, usage: Usage | None = None) -> ChatTurn:
    """A scripted final answer."""
    return ChatTurn(text=text, tool_calls=[], usage=usage or Usage(150, 40))
