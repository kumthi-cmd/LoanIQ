"""The LLMProvider interface and the neutral types every adapter speaks.

Where it sits:
    orchestrator -> [LLMProvider.chat] -> anthropic | openai | gemini | offline | fake

BUSINESS: Ask the Tape must not depend on one AI vendor. Every model gets the same
  question, the same tool list and the same rules, and gives back the same kind of
  answer: some text, some tool calls, and how many tokens it used (which is what
  it costs).
TECH:
  - Strategy pattern: LLMProvider is an abstract base class (ABC) with one method,
    chat(). Each vendor adapter subclasses it; the orchestrator never imports a
    vendor SDK.
  - Tools are defined once, as JSON Schema (ToolSpec). Each adapter translates
    them into its vendor's format and handles that vendor's prompt caching.
  - Messages are neutral too: UserText, AssistantTurn (a ChatTurn the model
    returned) and ToolResults. An AssistantTurn keeps the vendor's raw content
    (`raw`) so the adapter can send it back unchanged; Claude needs its thinking
    blocks returned exactly as it wrote them.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Union


class ProviderError(RuntimeError):
    """A provider could not answer: network, HTTP error, timeout, bad response.

    BUSINESS: the orchestrator answers with built-in rules instead and says why.
    TECH: adapters wrap their SDK's exceptions in this, so the orchestrator catches
      one class. `reason` is a short machine-readable code for the log and screen.
    """

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class ProviderUnavailable(ProviderError):
    """The provider is switched off: no API key in the environment."""

    def __init__(self, provider: str, env_var: str | None) -> None:
        super().__init__("unavailable", f"{provider} has no API key ({env_var} is not set)")


@dataclass(frozen=True)
class ToolSpec:
    """One tool, defined once for every provider.

    BUSINESS: "query_tape: run one read-only SELECT over the loan tape".
    TECH: input_schema is JSON Schema (type object, properties, required,
      additionalProperties false), which Claude, OpenAI and Gemini all accept.
    """
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    """The model asking LoanIQ to run a tool. TECH: id ties the result back to the call."""
    id: str
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    """What a tool gave back.

    TECH: content is the text the model reads (totals plus the first rows as CSV).
      is_error marks a refused or failed call; the model reads the reason and may
      try again. data is structured output for code that is not a model (the
      offline rules, tests); adapters never send it.
    """
    call_id: str
    name: str
    content: str
    is_error: bool = False
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class Usage:
    """Tokens used by one or more model calls.

    BUSINESS: tokens are what the model bills. Cache reads (the reused system
      prompt and tool list) cost a tenth of fresh input.
    TECH: input_tokens counts only uncached input. Adapters normalise to this:
      Anthropic reports it that way already; OpenAI and Gemini include cached
      tokens in their prompt count, so the adapter subtracts them.
    """
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def add(self, other: Usage) -> None:
        """Add another call's tokens to this running total (in place)."""
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_read_tokens += other.cache_read_tokens
        self.cache_write_tokens += other.cache_write_tokens

    def as_dict(self) -> dict[str, int]:
        """TECH: for JSON events and log lines."""
        return {"input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
                "cache_read_tokens": self.cache_read_tokens,
                "cache_write_tokens": self.cache_write_tokens}


@dataclass
class ChatTurn:
    """One model reply.

    TECH: stop_reason is normalised to "end_turn", "tool_use", "max_tokens" or
      "refusal". raw is the vendor's own content, kept for replay; None for
      offline and fake.
    """
    text: str
    tool_calls: list[ToolCall]
    usage: Usage
    stop_reason: str = "end_turn"
    raw: Any = None


@dataclass(frozen=True)
class UserText:
    """The visitor's question."""
    text: str


@dataclass(frozen=True)
class AssistantTurn:
    """A model reply, sent back to the model as history."""
    turn: ChatTurn


@dataclass(frozen=True)
class ToolResults:
    """Every result for one model reply, in one message.

    TECH: all results of a reply go back together; splitting them across messages
      teaches Claude to stop making parallel calls.
    """
    results: tuple[ToolResult, ...]


Message = Union[UserText, AssistantTurn, ToolResults]


@dataclass(frozen=True)
class ChatOptions:
    """Per-call settings beyond the interface's five arguments.

    TECH: timeout_s is the time left for the question (the orchestrator's 20 s
      budget minus what is spent); effort comes from llm.toml [models].
    """
    timeout_s: float = 20.0
    effort: str | None = None


class LLMProvider(ABC):
    """One way of getting a model reply. The Strategy interface.

    BUSINESS: anything that can read a question and the tool list, and answer with
      text or tool calls, can power Ask the Tape.
    TECH: name is the provider's key in llm.toml. available() is False when the
      provider has no API key; the orchestrator then uses the fallback provider.
    """

    name: str = "base"

    def available(self) -> bool:
        """True when this provider can be called now."""
        return True

    @abstractmethod
    def chat(self, system: str, messages: list[Message], tools: list[ToolSpec],
             model: str, max_tokens: int, options: ChatOptions = ChatOptions()) -> ChatTurn:
        """Send the conversation, get one reply.

        TECH: system is the system prompt; messages the history so far, oldest
          first; tools every tool the model may call; model the vendor's model id;
          max_tokens the output cap for this call (tokens). Raises ProviderError.
        """
