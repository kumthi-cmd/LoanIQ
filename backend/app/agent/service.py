"""Wire Ask the Tape together: config, read-only tape, tools, providers, orchestrator.

Where it sits:
    main.py lifespan -> [build_ask_service] -> app.state.ask -> agent/api.py routes
    scripts/eval_agent.py -> [build_ask_service] (same wiring, live models)

BUSINESS: one place that assembles the agent, so the live site, the tests and the
  golden-question evaluation all run exactly the same engine.
TECH: reads content/glossary.json (lookup_term), content/desk-questions.json (chip
  labels for the offline answers) and content/ask-the-tape.json (offline words and
  notices). providers can be injected (tests pass a FakeProvider as "anthropic").
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app import loan_tape_gen as gen
from app.agent.budget import SpendMeter
from app.agent.config import AgentConfig, load_agent_config
from app.agent.orchestrator import Orchestrator
from app.agent.providers.base import LLMProvider
from app.agent.providers.offline_provider import OfflineProvider
from app.agent.providers.registry import build_providers
from app.agent.query_store import QueryStore
from app.agent.tape_db import ReadOnlyTape, close_readonly_tape, open_readonly_tape
from app.agent.tools import TapeTools
from app.loan_query import ColumnTypes

CONTENT_DIR = gen.REPO_ROOT / "content"


def read_json(name: str) -> Any:
    """A file from content/ as JSON."""
    return json.loads((CONTENT_DIR / name).read_text(encoding="utf-8"))


@dataclass
class AskService:
    """Everything the /api/ask routes need. TECH: lives on app.state.ask."""
    cfg: AgentConfig
    orchestrator: Orchestrator
    store: QueryStore
    meter: SpendMeter
    tape: ReadOnlyTape


def build_ask_service(parquet_path: Path, columns: ColumnTypes, labels: dict[str, str],
                      desk_where: dict[str, str],
                      summarize: Callable[[], tuple[dict[str, Any], str]],
                      cfg: AgentConfig | None = None,
                      providers: dict[str, LLMProvider] | None = None) -> AskService:
    """Build the agent for one tape.

    TECH: desk_where is desk question id -> validated SQL rule (desk_questions.py).
      Injected providers replace the vendor adapters by name; offline is always
      LoanIQ's own.
    """
    cfg = cfg or load_agent_config()
    words = read_json("ask-the-tape.json")
    chip_labels = {q["id"]: q["label"] for q in read_json("desk-questions.json")["questions"]}
    offline = OfflineProvider(cfg.offline_rules, desk_where, chip_labels, words["offline"])
    tape = open_readonly_tape(parquet_path)
    store = QueryStore(cfg.limits.query_store_size, cfg.limits.query_store_ttl_s)
    tools = TapeTools(tape.con, columns, labels, read_json("glossary.json"), summarize, store, cfg.limits)
    meter = SpendMeter(cfg.budget)
    all_providers = {**build_providers(cfg, offline), **(providers or {}), "offline": offline}
    orchestrator = Orchestrator(cfg, all_providers, offline, tools, meter, words["notices"])
    return AskService(cfg=cfg, orchestrator=orchestrator, store=store, meter=meter, tape=tape)


def close_ask_service(service: AskService) -> None:
    """Close the read-only tape and delete its temporary file."""
    close_readonly_tape(service.tape)
