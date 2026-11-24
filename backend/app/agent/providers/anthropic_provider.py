"""The Claude adapter: LoanIQ's neutral chat -> Anthropic's Messages API.

Where it sits:
    orchestrator -> [AnthropicProvider.chat] -> api.anthropic.com/v1/messages

BUSINESS: the live model behind Ask the Tape (Claude Haiku 5.5, escalating to
  Claude Sonnet 5.5). The key comes only from the ANTHROPIC_API_KEY environment
  variable, set in the Render dashboard, never in Git.
TECH:
  - The official `anthropic` SDK, one non-streaming messages.create() per round;
    the orchestrator runs the loop itself, so it can check every tool call.
  - Tools are sent with strict: true, so the model's tool input always matches
    the JSON Schema. tool_choice stays "auto": forcing a tool is refused (HTTP 400)
    on Claude Sonnet 5.5.
  - Prompt caching: a cache_control mark on the system block. The API renders
    tools, then system, then messages, so one mark caches the tool list and the
    system prompt together (roughly 1,000 tokens by estimate, above Claude Haiku
    5.5's 512-token minimum; the eval script's "cache read" count confirms it on a
    live run). Both must stay byte-for-byte identical between calls, so nothing
    variable (dates, ids) ever goes in them. A cached read costs 0.1x input.
  - Effort ("low" in llm.toml) goes in output_config. Thinking is left at the
    model's default (adaptive).
  - The assistant's content is sent back exactly as received (`raw`), thinking
    blocks included: Claude checks that its own thinking is unchanged.
  - Stop reasons checked before reading content: "refusal" raises
    ProviderError("refusal") so built-in rules answer instead.
"""

from __future__ import annotations

import os
from typing import Any

from app.agent.providers.base import (AssistantTurn, ChatOptions, ChatTurn, LLMProvider, Message,
                                      ProviderError, ProviderUnavailable, ToolCall, ToolResults,
                                      ToolSpec, Usage, UserText)


def anthropic_tools(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    """ToolSpec -> Claude tool definitions. TECH: strict needs additionalProperties false."""
    return [{"name": t.name, "description": t.description, "input_schema": t.input_schema,
             "strict": True} for t in tools]


def anthropic_messages(messages: list[Message]) -> list[dict[str, Any]]:
    """Neutral history -> Claude's messages list.

    TECH: an AssistantTurn from Claude replays its raw content blocks (thinking and
      tool_use, unchanged). One from another provider (after a fallback) is sent
      as plain text plus tool_use blocks built from its tool calls.
    """
    out: list[dict[str, Any]] = []
    for m in messages:
        if isinstance(m, UserText):
            out.append({"role": "user", "content": m.text})
        elif isinstance(m, AssistantTurn):
            content = m.turn.raw if m.turn.raw is not None else rebuilt_content(m.turn)
            out.append({"role": "assistant", "content": content})
        elif isinstance(m, ToolResults):
            out.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": r.call_id, "content": r.content,
                 "is_error": r.is_error} for r in m.results]})
    return out


def rebuilt_content(turn: ChatTurn) -> list[dict[str, Any]]:
    """TECH: Claude content blocks for a turn that has no raw Claude content."""
    blocks: list[dict[str, Any]] = [{"type": "text", "text": turn.text}] if turn.text else []
    blocks += [{"type": "tool_use", "id": c.id, "name": c.name, "input": c.input}
               for c in turn.tool_calls]
    return blocks


def parse_response(resp: Any) -> ChatTurn:
    """A Claude Message -> ChatTurn.

    TECH: content is a list of typed blocks; check .type before reading fields.
      Thinking blocks are kept in raw but not shown. usage.input_tokens already
      excludes cached tokens.
    """
    if resp.stop_reason == "refusal":
        raise ProviderError("refusal", "Claude declined to answer this question")
    text = "".join(b.text for b in resp.content if b.type == "text")
    calls = [ToolCall(id=b.id, name=b.name, input=dict(b.input))
             for b in resp.content if b.type == "tool_use"]
    u = resp.usage
    usage = Usage(input_tokens=u.input_tokens or 0, output_tokens=u.output_tokens or 0,
                  cache_read_tokens=u.cache_read_input_tokens or 0,
                  cache_write_tokens=u.cache_creation_input_tokens or 0)
    # TECH: model_dump turns SDK block objects into plain dicts for replay.
    raw = [b.model_dump(exclude_none=True) for b in resp.content]
    return ChatTurn(text=text, tool_calls=calls, usage=usage,
                    stop_reason=resp.stop_reason or "end_turn", raw=raw)


class AnthropicProvider(LLMProvider):
    """Claude through the official SDK.

    BUSINESS: the production model for Ask the Tape.
    TECH: client may be injected (tests pass a fake with .messages.create); by
      default it is built on first use from the key in env_var. max_retries=1:
      the question has a 20 s budget, so one quick retry is all it can afford.
    """

    name = "anthropic"

    def __init__(self, env_var: str | None = "ANTHROPIC_API_KEY", client: Any = None) -> None:
        self.env_var = env_var
        self._client = client

    def available(self) -> bool:
        """TECH: True with an injected client or a non-empty key in the environment."""
        return self._client is not None or bool(self.env_var and os.environ.get(self.env_var))

    def client(self) -> Any:
        """The SDK client, built lazily so importing this module never needs a key."""
        if self._client is None:
            if not self.available():
                raise ProviderUnavailable(self.name, self.env_var)
            import anthropic  # TECH: imported here so tests and offline runs skip it
            self._client = anthropic.Anthropic(api_key=os.environ[str(self.env_var)], max_retries=1)
        return self._client

    def request(self, system: str, messages: list[Message], tools: list[ToolSpec],
                model: str, max_tokens: int, options: ChatOptions) -> dict[str, Any]:
        """The keyword arguments for messages.create (tests check this shape)."""
        params: dict[str, Any] = {
            "model": model, "max_tokens": max_tokens,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "tools": anthropic_tools(tools), "messages": anthropic_messages(messages),
            "timeout": options.timeout_s,
        }
        if options.effort:
            params["output_config"] = {"effort": options.effort}
        return params

    def chat(self, system: str, messages: list[Message], tools: list[ToolSpec],
             model: str, max_tokens: int, options: ChatOptions = ChatOptions()) -> ChatTurn:
        """One Claude round. TECH: every SDK error becomes ProviderError."""
        params = self.request(system, messages, tools, model, max_tokens, options)
        client = self.client()
        try:
            resp = client.messages.create(**params)
        except Exception as exc:  # TECH: SDK errors (HTTP, network, timeout) of any kind
            raise ProviderError(sdk_reason(exc), f"Claude call failed: {exc}") from exc
        return parse_response(resp)


def sdk_reason(exc: Exception) -> str:
    """A short reason code for an SDK exception: rate_limit, timeout, network, http_<code>.

    TECH: reads the class name and status_code rather than importing the SDK's
      classes, so the same function serves real and fake clients.
    """
    name = type(exc).__name__
    if "Timeout" in name:
        return "timeout"
    if "RateLimit" in name:
        return "rate_limit"
    if "Connection" in name:
        return "network"
    status = getattr(exc, "status_code", None)
    return f"http_{status}" if status else "error"
