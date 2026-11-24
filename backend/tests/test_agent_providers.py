"""Tests for the provider adapters: Anthropic, OpenAI, Gemini, Offline and Fake.

BUSINESS: the model behind Ask the Tape can be swapped. These tests protect that
  every adapter sends the same tools and rules in its vendor's format, reads tool
  calls and token counts back correctly (tokens are what LoanIQ pays for), keeps
  keys out of the code, and turns any vendor failure into a clean fallback.
TECH: no network. Each vendor adapter gets a fake client whose create() records
  the request and returns a response built from that vendor SDK's REAL response
  type (model_validate), so the parsing is checked against the actual shapes.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from anthropic.types import Message as AnthropicMessage
from google.genai import types as gtypes
from openai.types.chat import ChatCompletion

from app.agent.config import OfflineRule, load_agent_config
from app.agent.providers.anthropic_provider import AnthropicProvider, sdk_reason
from app.agent.providers.base import (AssistantTurn, ChatOptions, ChatTurn, ProviderError,
                                      ProviderUnavailable, ToolCall, ToolResult, ToolResults,
                                      Usage, UserText)
from app.agent.providers.fake_provider import FakeProvider, text_turn
from app.agent.providers.gemini_provider import GeminiProvider
from app.agent.providers.offline_provider import OfflineProvider, fmt_pct, fmt_usd, match_rule
from app.agent.providers.openai_provider import OpenAIProvider
from app.agent.providers.registry import build_providers
from app.agent.tools import TOOL_SPECS

HISTORY = [UserText("WAC of NY?"),
           AssistantTurn(ChatTurn("", [ToolCall("c1", "query_tape", {"title": "t", "sql": "SELECT 1"})],
                                  Usage(), "tool_use")),
           ToolResults((ToolResult("c1", "query_tape", "Error: bad", is_error=True),))]


class Recorder:
    """A fake SDK method: records keyword arguments, returns or raises a set value."""

    def __init__(self, result: Any) -> None:
        self.result, self.kwargs = result, {}

    def __call__(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


# =============================================================================
# Anthropic (the live provider)
# =============================================================================

def claude_message(content: list[dict], stop: str = "tool_use", **usage: int) -> AnthropicMessage:
    """A real anthropic Message object, as the API would return it."""
    return AnthropicMessage.model_validate({
        "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-haiku-5-5",
        "content": content, "stop_reason": stop, "stop_sequence": None,
        "usage": {"input_tokens": usage.get("inp", 50), "output_tokens": usage.get("out", 20),
                  "cache_read_input_tokens": usage.get("cr", 1400),
                  "cache_creation_input_tokens": usage.get("cw", 0)}})


def claude(result: Any) -> tuple[AnthropicProvider, Recorder]:
    """An AnthropicProvider over a fake client."""
    create = Recorder(result)
    return AnthropicProvider(client=SimpleNamespace(messages=SimpleNamespace(create=create))), create


def test_anthropic_request_caches_strict_tools_and_sets_effort() -> None:
    """BUSINESS: the tool list and rules are cached (a tenth of the input price on
    every later call), tool inputs must match their schemas, and effort is "low".

    TECH: cache_control on the system block caches tools + system together;
      strict on every tool; tool_choice left out (auto); the refused call goes back
      as an is_error tool_result.
    """
    provider, create = claude(claude_message([{"type": "text", "text": "Done."}], "end_turn"))
    provider.chat("SYSTEM", HISTORY, TOOL_SPECS, "claude-haiku-5-5", 800,
                  ChatOptions(timeout_s=12.5, effort="low"))
    kw = create.kwargs
    assert kw["system"] == [{"type": "text", "text": "SYSTEM", "cache_control": {"type": "ephemeral"}}]
    assert all(t["strict"] is True for t in kw["tools"]) and "tool_choice" not in kw
    assert kw["output_config"] == {"effort": "low"} and kw["max_tokens"] == 800 and kw["timeout"] == 12.5
    assert kw["messages"][1]["content"][0]["type"] == "tool_use"
    assert kw["messages"][2]["content"][0] == {"type": "tool_result", "tool_use_id": "c1",
                                               "content": "Error: bad", "is_error": True}


def test_anthropic_parses_tool_calls_and_usage_and_replays_raw_blocks() -> None:
    """BUSINESS: token counts are read exactly, cache reads separately (they cost less).

    TECH: thinking blocks are kept in raw and sent back unchanged next round.
    """
    msg = claude_message([{"type": "thinking", "thinking": "", "signature": "sig"},
                          {"type": "tool_use", "id": "tu1", "name": "summarize_tape", "input": {}}])
    provider, create = claude(msg)
    turn = provider.chat("S", [UserText("q")], TOOL_SPECS, "claude-haiku-5-5", 800)
    assert turn.tool_calls == [ToolCall("tu1", "summarize_tape", {})] and turn.stop_reason == "tool_use"
    assert turn.usage == Usage(input_tokens=50, output_tokens=20, cache_read_tokens=1400)
    provider.chat("S", [UserText("q"), AssistantTurn(turn)], TOOL_SPECS, "claude-haiku-5-5", 800)
    replayed = create.kwargs["messages"][1]["content"]
    assert replayed[0]["type"] == "thinking" and replayed[0]["signature"] == "sig"


def test_anthropic_refusal_and_errors_become_provider_errors() -> None:
    """BUSINESS: a declined question or a failed call hands over to built-in rules."""
    provider, _ = claude(claude_message([], "refusal"))
    with pytest.raises(ProviderError) as refusal:
        provider.chat("S", [UserText("q")], TOOL_SPECS, "m", 800)
    assert refusal.value.reason == "refusal"

    class RateLimitError(Exception):
        """Named like the SDK's class; sdk_reason reads the name."""
    provider, _ = claude(RateLimitError("slow down"))
    with pytest.raises(ProviderError) as limited:
        provider.chat("S", [UserText("q")], TOOL_SPECS, "m", 800)
    assert limited.value.reason == "rate_limit"


@pytest.mark.parametrize("name, status, reason", [
    ("APITimeoutError", None, "timeout"), ("APIConnectionError", None, "network"),
    ("InternalServerError", 529, "http_529"), ("ValueError", None, "error"),
])
def test_sdk_reason_codes(name: str, status: int | None, reason: str) -> None:
    """TECH: the short reason in logs and on screen, from the exception's class."""
    exc = type(name, (Exception,), {})()
    exc.status_code = status
    assert sdk_reason(exc) == reason


def test_keys_come_only_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """BUSINESS: no key in the code; with no key set the provider is simply off."""
    monkeypatch.delenv("LOANIQ_TEST_KEY", raising=False)
    for cls in (AnthropicProvider, OpenAIProvider, GeminiProvider):
        provider = cls("LOANIQ_TEST_KEY")
        assert not provider.available()
        with pytest.raises(ProviderUnavailable):
            provider.chat("S", [UserText("q")], TOOL_SPECS, "m", 800)
    monkeypatch.setenv("LOANIQ_TEST_KEY", "sk-test")
    assert AnthropicProvider("LOANIQ_TEST_KEY").available()


def test_real_sdk_clients_are_built_from_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """TECH: with a key set, each adapter builds its vendor's real client (no call made)."""
    monkeypatch.setenv("LOANIQ_TEST_KEY", "sk-test")
    import anthropic
    import openai
    from google import genai
    assert isinstance(AnthropicProvider("LOANIQ_TEST_KEY").client(), anthropic.Anthropic)
    assert isinstance(OpenAIProvider("LOANIQ_TEST_KEY").client(), openai.OpenAI)
    assert isinstance(GeminiProvider("LOANIQ_TEST_KEY").client(), genai.Client)


def test_registry_builds_every_provider_from_config() -> None:
    """BUSINESS: switching vendor is a config change. TECH: names match llm.toml."""
    offline = FakeProvider()
    providers = build_providers(load_agent_config(), offline)
    assert set(providers) == {"anthropic", "openai", "gemini", "offline"}
    assert providers["offline"] is offline and providers["anthropic"].env_var == "ANTHROPIC_API_KEY"


# =============================================================================
# OpenAI (off by default)
# =============================================================================

def completion(message: dict, finish: str = "tool_calls", cached: int = 0) -> ChatCompletion:
    """A real openai ChatCompletion object."""
    return ChatCompletion.model_validate({
        "id": "c1", "object": "chat.completion", "created": 0, "model": "gpt-test",
        "choices": [{"index": 0, "finish_reason": finish, "message": {"role": "assistant", **message}}],
        "usage": {"prompt_tokens": 1000, "completion_tokens": 30, "total_tokens": 1030,
                  "prompt_tokens_details": {"cached_tokens": cached}}})


def gpt(result: Any) -> tuple[OpenAIProvider, Recorder]:
    """An OpenAIProvider over a fake client."""
    create = Recorder(result)
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return OpenAIProvider(client=client), create


def test_openai_translates_tools_and_history() -> None:
    """TECH: function tools with strict; system first; tool results as role "tool";
    effort as reasoning_effort; max_completion_tokens as the cap."""
    provider, create = gpt(completion({"content": "Done."}, "stop"))
    turn = provider.chat("SYSTEM", HISTORY, TOOL_SPECS, "gpt-test", 800, ChatOptions(effort="low"))
    kw = create.kwargs
    assert kw["tools"][1]["function"]["name"] == "query_tape" and kw["tools"][1]["function"]["strict"]
    assert kw["messages"][0] == {"role": "system", "content": "SYSTEM"}
    assert kw["messages"][2]["tool_calls"][0]["function"]["arguments"] == '{"title": "t", "sql": "SELECT 1"}'
    assert kw["messages"][3] == {"role": "tool", "tool_call_id": "c1", "content": "Error: bad"}
    assert kw["reasoning_effort"] == "low" and kw["max_completion_tokens"] == 800
    assert turn.text == "Done." and turn.stop_reason == "end_turn"


def test_openai_parses_calls_and_subtracts_cached_tokens() -> None:
    """BUSINESS: cached tokens are counted once, at the cheaper cache price."""
    call = {"id": "k1", "type": "function", "function": {"name": "get_loan", "arguments": '{"loan_id": "LN00000001"}'}}
    provider, _ = gpt(completion({"content": None, "tool_calls": [call]}, cached=800))
    turn = provider.chat("S", [UserText("q")], TOOL_SPECS, "gpt-test", 800)
    assert turn.tool_calls == [ToolCall("k1", "get_loan", {"loan_id": "LN00000001"})]
    assert turn.usage == Usage(input_tokens=200, output_tokens=30, cache_read_tokens=800)


@pytest.mark.parametrize("message, finish, reason", [
    ({"content": None, "tool_calls": [{"id": "k", "type": "function",
                                        "function": {"name": "get_loan", "arguments": "{bad"}}]},
     "tool_calls", "bad_tool_input"),
    ({"content": "no"}, "content_filter", "refusal"),
])
def test_openai_bad_json_and_refusal(message: dict, finish: str, reason: str) -> None:
    """BUSINESS: a half-read tool call is never run; a declined question falls back."""
    provider, _ = gpt(completion(message, finish))
    with pytest.raises(ProviderError) as err:
        provider.chat("S", [UserText("q")], TOOL_SPECS, "gpt-test", 800)
    assert err.value.reason == reason


def test_openai_sdk_errors_become_provider_errors() -> None:
    """TECH: any exception from the SDK call becomes ProviderError."""
    provider, _ = gpt(RuntimeError("boom"))
    with pytest.raises(ProviderError):
        provider.chat("S", [UserText("q")], TOOL_SPECS, "gpt-test", 800)


# =============================================================================
# Gemini (off by default)
# =============================================================================

def generation(parts: list[dict], finish: str = "STOP", candidates: bool = True) -> gtypes.GenerateContentResponse:
    """A real google-genai GenerateContentResponse object."""
    return gtypes.GenerateContentResponse.model_validate({
        "candidates": [{"content": {"role": "model", "parts": parts}, "finish_reason": finish}] if candidates else [],
        "usage_metadata": {"prompt_token_count": 1000, "cached_content_token_count": 600,
                           "candidates_token_count": 40, "thoughts_token_count": 10}})


def gemini(result: Any) -> tuple[GeminiProvider, Recorder]:
    """A GeminiProvider over a fake client."""
    create = Recorder(result)
    return GeminiProvider(client=SimpleNamespace(models=SimpleNamespace(generate_content=create))), create


def test_gemini_never_runs_tools_itself_and_translates_history() -> None:
    """BUSINESS: every Gemini tool call still passes LoanIQ's guardrails.

    TECH: automatic function calling disabled; JSON Schema passed as is; the tool
      result goes back as a function response part; timeout in milliseconds.
    """
    provider, create = gemini(generation([{"text": "Done."}]))
    turn = provider.chat("SYSTEM", HISTORY, TOOL_SPECS, "gemini-test", 800, ChatOptions(timeout_s=10))
    config = create.kwargs["config"]
    assert config.automatic_function_calling.disable is True and config.system_instruction == "SYSTEM"
    assert config.tools[0].function_declarations[1].parameters_json_schema == TOOL_SPECS[1].input_schema
    assert config.max_output_tokens == 800 and config.http_options.timeout == 10_000
    contents = create.kwargs["contents"]
    assert contents[1].parts[0].function_call.name == "query_tape"
    assert contents[2].parts[0].function_response.response == {"error": "Error: bad"}
    assert turn.text == "Done."


def test_gemini_parses_calls_and_usage() -> None:
    """BUSINESS: thinking tokens are billed as output, cached tokens counted once.

    TECH: a call without an id gets one from its position.
    """
    provider, _ = gemini(generation([{"function_call": {"name": "summarize_tape", "args": {}}}]))
    turn = provider.chat("S", [UserText("q")], TOOL_SPECS, "gemini-test", 800)
    assert turn.tool_calls == [ToolCall("call_0", "summarize_tape", {})] and turn.stop_reason == "tool_use"
    assert turn.usage == Usage(input_tokens=400, output_tokens=50, cache_read_tokens=600)
    assert turn.raw.role == "model"


@pytest.mark.parametrize("response", [generation([], "SAFETY"), generation([], candidates=False)])
def test_gemini_refusals(response: Any) -> None:
    """BUSINESS: a blocked or empty answer falls back to built-in rules."""
    provider, _ = gemini(response)
    with pytest.raises(ProviderError) as err:
        provider.chat("S", [UserText("q")], TOOL_SPECS, "gemini-test", 800)
    assert err.value.reason == "refusal"


def test_gemini_sdk_errors_become_provider_errors() -> None:
    """TECH: any exception from the SDK call becomes ProviderError."""
    provider, _ = gemini(RuntimeError("boom"))
    with pytest.raises(ProviderError):
        provider.chat("S", [UserText("q")], TOOL_SPECS, "gemini-test", 800)


def test_cross_provider_history_is_rebuilt() -> None:
    """TECH: a turn with no raw vendor content (written by another provider) is
    rebuilt as text plus tool calls for Claude and for Gemini."""
    turn = ChatTurn("thinking aloud", [ToolCall("c1", "summarize_tape", {})], Usage())
    provider, create = claude(claude_message([{"type": "text", "text": "ok"}], "end_turn"))
    provider.chat("S", [UserText("q"), AssistantTurn(turn)], TOOL_SPECS, "m", 800)
    assert [b["type"] for b in create.kwargs["messages"][1]["content"]] == ["text", "tool_use"]
    g, gcreate = gemini(generation([{"text": "ok"}]))
    g.chat("S", [UserText("q"), AssistantTurn(turn)], TOOL_SPECS, "m", 800)
    assert gcreate.kwargs["contents"][1].role == "model"


# =============================================================================
# Offline rules and the Fake
# =============================================================================

RULES = (OfflineRule("desk_question", "new_york", ("new york", " ny ")),
         OfflineRule("summary", "summary", ("summar",)))


@pytest.mark.parametrize("question, rule_id", [
    ("How many loans in NY?", "new_york"), ("new york loans", "new_york"),
    ("Is there any data?", None), ("Summarize the tape", "summary"),
])
def test_offline_rule_matching(question: str, rule_id: str | None) -> None:
    """BUSINESS: "NY" means New York, but "any" does not."""
    rule = match_rule(question, RULES)
    assert (rule.id if rule else None) == rule_id


def test_offline_unknown_question_explains_what_it_can_answer() -> None:
    """BUSINESS: built-in rules say what they can answer instead of guessing."""
    offline = OfflineProvider(RULES, {"new_york": "state = 'NY'"}, {}, {"no_match": "I answer desk questions."})
    assert offline.chat("S", [UserText("tell me a joke")], TOOL_SPECS, "offline", 800).text == "I answer desk questions."


def test_offline_pinned_desk_question_without_a_keyword_rule() -> None:
    """BUSINESS: every desk-question chip works, even one with no keyword rule."""
    offline = OfflineProvider(RULES, {"modified": "mod_flag = TRUE"}, {"modified": "Modified"}, {})
    turn = offline.pinned("modified").chat("S", [UserText("")], TOOL_SPECS, "offline", 800)
    assert [c.input["title"] for c in turn.tool_calls] == ["Modified: totals", "Modified: loans"]
    assert "WHERE mod_flag = TRUE" in turn.tool_calls[0].input["sql"]


@pytest.mark.parametrize("value, text", [(638_337_753.05, "$638.3M"), (3_512_345, "$3.5M"),
                                         (1_250_000_000, "$1.25B"), (412_500, "$412.5K"), (812.34, "$812.34")])
def test_dollar_format(value: float, text: str) -> None:
    """BUSINESS: dollars as a desk writes them."""
    assert fmt_usd(value) == text


def test_percent_format() -> None:
    """BUSINESS: rates with three decimals; a dash when there is no value."""
    assert fmt_pct(6.4123, 3) == "6.412%" and fmt_pct(None, 3) == "-"


def test_fake_runs_its_script_then_stops() -> None:
    """TECH: scripted turns, a scripted error, then "script_ended"."""
    fake = FakeProvider([text_turn("one"), ProviderError("timeout", "slow")])
    assert fake.chat("S", [UserText("q")], TOOL_SPECS, "m", 800).text == "one"
    for reason in ("timeout", "script_ended"):
        with pytest.raises(ProviderError) as err:
            fake.chat("S", [UserText("q")], TOOL_SPECS, "m", 800)
        assert err.value.reason == reason
    assert len(fake.calls) == 3 and fake.calls[0].model == "m"
