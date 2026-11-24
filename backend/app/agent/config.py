"""Load and check config/llm.toml: tasks, providers, model prices, limits, budget.

Where it sits:
    config/llm.toml -> [agent.config] -> orchestrator, providers, tools, budget

BUSINESS: one file decides which model answers Ask the Tape, what it may cost and
  how long it may take. Every number in it is illustrative.
TECH: the TOML is turned into frozen dataclasses once, when the API starts, so a
  typo (a task naming an unknown provider, a model with no price) stops start-up
  with a clear message instead of failing on a visitor's first question.
  Prices are Decimal (dollars per million tokens): costs are money, and money is
  never computed in float here (.claude/rules/python.md).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

LLM_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "llm.toml"

# TECH: the providers the code knows how to build (providers/registry.py).
KNOWN_PROVIDERS = ("anthropic", "openai", "gemini", "offline", "fake")
OFFLINE_KINDS = ("desk_question", "summary")


@dataclass(frozen=True)
class TaskRoute:
    """Which provider and model answer one kind of request.

    BUSINESS: tape questions go to Claude Haiku 5.5, move up to Claude Sonnet 5.5
      after repeated refused tool calls, and fall back to built-in rules.
    TECH: escalation_model runs on the same provider as model.
    """
    provider: str
    model: str
    escalation_model: str
    escalate_after: int
    fallback_provider: str


@dataclass(frozen=True)
class ModelPrice:
    """A model's request settings and prices.

    BUSINESS: what one million tokens cost: input (the question, tools and
      results the model reads), output (what it writes), cache read and cache write
      (the reused system prompt and tool list). Illustrative, from llm.toml.
    TECH: dollars per million tokens, Decimal. effort is passed to the provider
      ("low" ... "max") or None to use the model default.
    """
    input: Decimal
    output: Decimal
    cache_read: Decimal
    cache_write: Decimal
    effort: str | None = None


@dataclass(frozen=True)
class Limits:
    """Per-question limits. TECH: units in each field name (s, ms, chars, rows)."""
    max_rounds: int
    max_output_tokens: int
    question_timeout_s: float
    max_question_chars: int
    max_rows: int
    query_timeout_ms: int
    max_sql_chars: int
    rows_to_model: int
    query_store_size: int
    query_store_ttl_s: float


@dataclass(frozen=True)
class Budget:
    """Spending limits. BUSINESS: dollars per UTC day and questions per visitor per day."""
    daily_cap_usd: Decimal
    questions_per_visitor_per_day: int
    trust_forwarded_for: bool


@dataclass(frozen=True)
class OfflineRule:
    """One built-in rule: question keywords -> a desk question or the tape summary.

    BUSINESS: lets the desk's common questions be answered with no model at all.
    TECH: keywords are lower case; the question is lower-cased and padded with
      spaces before matching, so " ny" matches "loans in NY" but not "any".
    """
    kind: str
    id: str
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class AgentConfig:
    """Everything in llm.toml, checked."""
    tasks: dict[str, TaskRoute]
    provider_keys: dict[str, str | None]
    models: dict[str, ModelPrice]
    limits: Limits
    budget: Budget
    offline_rules: tuple[OfflineRule, ...]

    def price(self, model: str) -> ModelPrice:
        """The price of a model. TECH: KeyError names the model if it has no price."""
        if model not in self.models:
            raise KeyError(f"No [models.{model}] prices in llm.toml")
        return self.models[model]


def parse_task(name: str, raw: dict[str, Any]) -> TaskRoute:
    """One [tasks.<name>] table -> TaskRoute. TECH: raises ValueError on a bad provider."""
    route = TaskRoute(provider=raw["provider"], model=raw["model"],
                      escalation_model=raw.get("escalation_model", raw["model"]),
                      escalate_after=int(raw.get("escalate_after_guardrail_failures", 0)),
                      fallback_provider=raw.get("fallback_provider", "offline"))
    for provider in (route.provider, route.fallback_provider):
        if provider not in KNOWN_PROVIDERS:
            raise ValueError(f"Task {name}: unknown provider {provider!r}")
    return route


def parse_price(raw: dict[str, Any]) -> ModelPrice:
    """One [models.<id>] table -> ModelPrice.

    TECH: Decimal(str(x)) turns the TOML float 0.10 into exactly 0.10, not the
      nearest binary float.
    """
    money = {k: Decimal(str(raw[k])) for k in ("input", "output", "cache_read", "cache_write")}
    if any(v < 0 for v in money.values()):
        raise ValueError("Model prices must not be negative")
    return ModelPrice(**money, effort=raw.get("effort"))


def parse_offline_rules(raw: list[dict[str, Any]]) -> tuple[OfflineRule, ...]:
    """The [[offline.rule]] list -> OfflineRule tuple, in file order."""
    rules = []
    for entry in raw:
        if entry.get("kind") not in OFFLINE_KINDS:
            raise ValueError(f"Offline rule {entry.get('id')}: kind must be one of {OFFLINE_KINDS}")
        keywords = tuple(str(k).lower() for k in entry.get("keywords", []))
        if not keywords:
            raise ValueError(f"Offline rule {entry.get('id')}: needs at least one keyword")
        rules.append(OfflineRule(kind=entry["kind"], id=entry["id"], keywords=keywords))
    return tuple(rules)


def parse_config(raw: dict[str, Any]) -> AgentConfig:
    """The whole llm.toml dict -> AgentConfig, with cross-checks.

    TECH: every model a task can run must have a price, so cost logging and the
      daily cap can never silently count a question as free.
    """
    tasks = {name: parse_task(name, t) for name, t in raw["tasks"].items()}
    models = {mid: parse_price(m) for mid, m in raw.get("models", {}).items()}
    for name, task in tasks.items():
        if task.provider in ("offline", "fake"):
            continue
        for model in (task.model, task.escalation_model):
            if model not in models:
                raise ValueError(f"Task {name}: model {model!r} has no [models] prices")
    providers = {name: p.get("api_key_env") for name, p in raw.get("providers", {}).items()}
    lim, bud = raw["limits"], raw["budget"]
    limits = Limits(**{k: lim[k] for k in Limits.__dataclass_fields__})
    budget = Budget(daily_cap_usd=Decimal(str(bud["daily_cap_usd"])),
                    questions_per_visitor_per_day=int(bud["questions_per_visitor_per_day"]),
                    trust_forwarded_for=bool(bud.get("trust_forwarded_for", False)))
    rules = parse_offline_rules(raw.get("offline", {}).get("rule", []))
    return AgentConfig(tasks=tasks, provider_keys=providers, models=models,
                       limits=limits, budget=budget, offline_rules=rules)


def load_agent_config(path: Path = LLM_CONFIG_PATH) -> AgentConfig:
    """Read and check llm.toml. TECH: tomllib needs the file opened in binary mode."""
    with path.open("rb") as f:
        return parse_config(tomllib.load(f))
