"""Build every provider named in llm.toml, keyed by name.

Where it sits:
    config (llm.toml [providers]) -> [build_providers] -> orchestrator picks by task

BUSINESS: switching Ask the Tape to another vendor is a config change: name a
  different provider and model under [tasks.tape_query] and set that vendor's key.
TECH: the vendor adapters are built without contacting anyone; each builds its SDK
  client on first use, and only if its environment variable holds a key. The
  offline provider is built by the caller (it needs the desk questions and the
  content words) and passed in.
"""

from __future__ import annotations

from app.agent.config import AgentConfig
from app.agent.providers.anthropic_provider import AnthropicProvider
from app.agent.providers.base import LLMProvider
from app.agent.providers.gemini_provider import GeminiProvider
from app.agent.providers.openai_provider import OpenAIProvider


def build_providers(cfg: AgentConfig, offline: LLMProvider) -> dict[str, LLMProvider]:
    """name -> provider, for anthropic, openai, gemini and offline."""
    keys = cfg.provider_keys
    return {
        "anthropic": AnthropicProvider(keys.get("anthropic", "ANTHROPIC_API_KEY")),
        "openai": OpenAIProvider(keys.get("openai", "OPENAI_API_KEY")),
        "gemini": GeminiProvider(keys.get("gemini", "GEMINI_API_KEY")),
        "offline": offline,
    }
