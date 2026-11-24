"""The Gemini adapter: LoanIQ's neutral chat -> Google's Gen AI SDK. Off by default.

Where it sits:
    orchestrator -> [GeminiProvider.chat] -> Gemini API (only when a task names it)

BUSINESS: the third swappable model. Runs only when GEMINI_API_KEY is set and a
  task in llm.toml names provider "gemini".
TECH:
  - The official `google-genai` SDK: client.models.generate_content(), one call
    per round, with automatic function calling switched OFF, so the SDK never runs
    a tool by itself and every call passes LoanIQ's guardrails.
  - Tools: one types.Tool holding a FunctionDeclaration per tool, with the JSON
    Schema passed as parameters_json_schema (no translation needed).
  - Roles are "user" and "model". Gemini's own reply Content is replayed as is
    (`raw`), keeping its thought signatures. Tool results go back as function
    response parts, in one "user" Content.
  - Prompt caching is implicit on Gemini for repeated prefixes. Its usage includes
    cached tokens in prompt_token_count; they are subtracted here. Thinking tokens
    are billed as output, so they are added to output_tokens.
"""

from __future__ import annotations

import os
from typing import Any

from app.agent.providers.base import (AssistantTurn, ChatOptions, ChatTurn, LLMProvider, Message,
                                      ProviderError, ProviderUnavailable, ToolCall, ToolResults,
                                      ToolSpec, Usage, UserText, sdk_error)

# TECH: Gemini finish reasons that mean "declined" or "cut short".
REFUSAL_REASONS = {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION"}


def gemini_contents(messages: list[Message]) -> list[Any]:
    """Neutral history -> a list of types.Content."""
    from google.genai import types
    out: list[Any] = []
    for m in messages:
        if isinstance(m, UserText):
            out.append(types.Content(role="user", parts=[types.Part(text=m.text)]))
        elif isinstance(m, AssistantTurn):
            out.append(m.turn.raw if m.turn.raw is not None else rebuilt_content(m.turn))
        elif isinstance(m, ToolResults):
            parts = [types.Part.from_function_response(
                name=r.name, response={"error" if r.is_error else "result": r.content})
                for r in m.results]
            out.append(types.Content(role="user", parts=parts))
    return out


def rebuilt_content(turn: ChatTurn) -> Any:
    """TECH: a "model" Content for a turn that has no raw Gemini content (after a fallback)."""
    from google.genai import types
    parts = [types.Part(text=turn.text)] if turn.text else []
    parts += [types.Part(function_call=types.FunctionCall(id=c.id, name=c.name, args=c.input))
              for c in turn.tool_calls]
    return types.Content(role="model", parts=parts)


def gemini_config(system: str, tools: list[ToolSpec], max_tokens: int,
                  options: ChatOptions) -> Any:
    """The GenerateContentConfig: system prompt, tools, output cap, no auto-calling.

    TECH: http_options timeout is in milliseconds in this SDK.
    """
    from google.genai import types
    decls = [types.FunctionDeclaration(name=t.name, description=t.description,
                                       parameters_json_schema=t.input_schema) for t in tools]
    return types.GenerateContentConfig(
        system_instruction=system, tools=[types.Tool(function_declarations=decls)],
        max_output_tokens=max_tokens,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        http_options=types.HttpOptions(timeout=int(options.timeout_s * 1000)))


def parse_generation(resp: Any) -> ChatTurn:
    """A GenerateContentResponse -> ChatTurn.

    TECH: Gemini may omit a call id; one is made from the position so results can
      still be matched in LoanIQ's history.
    """
    if not resp.candidates:
        raise ProviderError("refusal", "Gemini returned no answer")
    cand = resp.candidates[0]
    reason = str(getattr(cand.finish_reason, "name", cand.finish_reason or "STOP"))
    if reason in REFUSAL_REASONS:
        raise ProviderError("refusal", f"Gemini declined to answer ({reason})")
    parts = (cand.content.parts or []) if cand.content else []
    text = "".join(p.text for p in parts if getattr(p, "text", None) and not getattr(p, "thought", False))
    calls = [ToolCall(id=p.function_call.id or f"call_{i}", name=p.function_call.name,
                      input=dict(p.function_call.args or {}))
             for i, p in enumerate(parts) if getattr(p, "function_call", None)]
    u = resp.usage_metadata
    cached = (u.cached_content_token_count or 0) if u else 0
    usage = Usage(input_tokens=((u.prompt_token_count or 0) - cached) if u else 0,
                  output_tokens=((u.candidates_token_count or 0) + (u.thoughts_token_count or 0)) if u else 0,
                  cache_read_tokens=cached)
    stop = "tool_use" if calls else ("max_tokens" if reason == "MAX_TOKENS" else "end_turn")
    return ChatTurn(text=text, tool_calls=calls, usage=usage, stop_reason=stop, raw=cand.content)


class GeminiProvider(LLMProvider):
    """Gemini models through the official SDK. TECH: client injectable for tests."""

    name = "gemini"

    def __init__(self, env_var: str | None = "GEMINI_API_KEY", client: Any = None) -> None:
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
            from google import genai
            self._client = genai.Client(api_key=os.environ[str(self.env_var)])
        return self._client

    def chat(self, system: str, messages: list[Message], tools: list[ToolSpec],
             model: str, max_tokens: int, options: ChatOptions = ChatOptions()) -> ChatTurn:
        """One Gemini round. TECH: every SDK error becomes ProviderError."""
        config = gemini_config(system, tools, max_tokens, options)
        contents = gemini_contents(messages)
        client = self.client()
        try:
            resp = client.models.generate_content(model=model, contents=contents, config=config)
        except Exception as exc:
            raise sdk_error(exc, "Gemini") from exc
        return parse_generation(resp)
