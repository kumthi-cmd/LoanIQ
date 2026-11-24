"""The OpenAI adapter: LoanIQ's neutral chat -> OpenAI Chat Completions. Off by default.

Where it sits:
    orchestrator -> [OpenAIProvider.chat] -> api.openai.com (only when a task names it)

BUSINESS: shows the model behind Ask the Tape can be swapped. It runs only when
  OPENAI_API_KEY is set and a task in llm.toml names provider "openai".
TECH:
  - The official `openai` SDK, chat.completions.create(), one call per round.
  - Tools become {"type": "function", "function": {name, description, parameters,
    strict: true}}. OpenAI's strict mode also needs every property listed in
    "required"; LoanIQ's tool schemas already do that.
  - The system prompt is the first message (role "system"). Tool results go back
    as one role "tool" message per call, matched by tool_call_id.
  - Tool arguments arrive as a JSON string and are parsed here; bad JSON raises
    ProviderError instead of running a half-read call.
  - Prompt caching is automatic on OpenAI for repeated prefixes; nothing to mark.
    Its usage counts cached tokens inside prompt_tokens, so they are subtracted
    to match LoanIQ's Usage (input_tokens = uncached only).
"""

from __future__ import annotations

import json
import os
from typing import Any

from app.agent.providers.base import (AssistantTurn, ChatOptions, ChatTurn, LLMProvider, Message,
                                      ProviderError, ProviderUnavailable, ToolCall, ToolResults,
                                      ToolSpec, Usage, UserText, sdk_error)

# TECH: OpenAI finish_reason -> LoanIQ's neutral stop_reason.
FINISH_REASONS = {"stop": "end_turn", "tool_calls": "tool_use", "length": "max_tokens",
                  "content_filter": "refusal"}


def openai_tools(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    """ToolSpec -> OpenAI function tools."""
    return [{"type": "function", "function": {"name": t.name, "description": t.description,
                                              "parameters": t.input_schema, "strict": True}}
            for t in tools]


def openai_messages(system: str, messages: list[Message]) -> list[dict[str, Any]]:
    """Neutral history -> OpenAI messages. TECH: arguments are sent back as JSON text."""
    out: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for m in messages:
        if isinstance(m, UserText):
            out.append({"role": "user", "content": m.text})
        elif isinstance(m, AssistantTurn):
            msg: dict[str, Any] = {"role": "assistant", "content": m.turn.text or None}
            if m.turn.tool_calls:
                msg["tool_calls"] = [{"id": c.id, "type": "function",
                                      "function": {"name": c.name, "arguments": json.dumps(c.input)}}
                                     for c in m.turn.tool_calls]
            out.append(msg)
        elif isinstance(m, ToolResults):
            out += [{"role": "tool", "tool_call_id": r.call_id, "content": r.content}
                    for r in m.results]
    return out


def parse_completion(resp: Any) -> ChatTurn:
    """An OpenAI ChatCompletion -> ChatTurn. TECH: raises ProviderError on bad JSON arguments."""
    choice = resp.choices[0]
    stop = FINISH_REASONS.get(choice.finish_reason or "stop", "end_turn")
    if stop == "refusal" or getattr(choice.message, "refusal", None):
        raise ProviderError("refusal", "The model declined to answer this question")
    calls = []
    for tc in choice.message.tool_calls or []:
        try:
            args = json.loads(tc.function.arguments or "{}")
        except json.JSONDecodeError as exc:
            raise ProviderError("bad_tool_input", f"Tool arguments were not JSON: {exc}") from exc
        calls.append(ToolCall(id=tc.id, name=tc.function.name, input=args))
    u = resp.usage
    details = getattr(u, "prompt_tokens_details", None)
    cached = (getattr(details, "cached_tokens", 0) or 0) if details else 0
    usage = Usage(input_tokens=(u.prompt_tokens or 0) - cached,
                  output_tokens=u.completion_tokens or 0, cache_read_tokens=cached)
    return ChatTurn(text=choice.message.content or "", tool_calls=calls, usage=usage,
                    stop_reason=stop)


class OpenAIProvider(LLMProvider):
    """ChatGPT models through the official SDK. TECH: client injectable for tests."""

    name = "openai"

    def __init__(self, env_var: str | None = "OPENAI_API_KEY", client: Any = None) -> None:
        self.env_var = env_var
        self._client = client

    def available(self) -> bool:
        """TECH: True with an injected client or a non-empty key in the environment."""
        return self._client is not None or bool(self.env_var and os.environ.get(self.env_var))

    def client(self) -> Any:
        """The SDK client, built lazily from the key."""
        if self._client is None:
            if not self.available():
                raise ProviderUnavailable(self.name, self.env_var)
            import openai
            self._client = openai.OpenAI(api_key=os.environ[str(self.env_var)], max_retries=1)
        return self._client

    def request(self, system: str, messages: list[Message], tools: list[ToolSpec],
                model: str, max_tokens: int, options: ChatOptions) -> dict[str, Any]:
        """Keyword arguments for chat.completions.create.

        TECH: max_completion_tokens (not the older max_tokens) caps output plus any
          reasoning tokens. effort maps to reasoning_effort for reasoning models.
        """
        params: dict[str, Any] = {"model": model, "max_completion_tokens": max_tokens,
                                  "messages": openai_messages(system, messages),
                                  "tools": openai_tools(tools), "timeout": options.timeout_s}
        if options.effort:
            params["reasoning_effort"] = options.effort
        return params

    def chat(self, system: str, messages: list[Message], tools: list[ToolSpec],
             model: str, max_tokens: int, options: ChatOptions = ChatOptions()) -> ChatTurn:
        """One OpenAI round. TECH: every SDK error becomes ProviderError."""
        params = self.request(system, messages, tools, model, max_tokens, options)
        client = self.client()
        try:
            resp = client.chat.completions.create(**params)
        except Exception as exc:
            raise sdk_error(exc, "OpenAI") from exc
        return parse_completion(resp)
