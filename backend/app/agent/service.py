"""Wire Ask the Tape together: config, read-only tape, tools, providers, orchestrator.

Where it sits:
    main.py lifespan -> [build_ask_service] -> app.state.ask -> agent/api.py routes
    scripts/eval_agent.py -> [build_ask_service] (same wiring, live models)

BUSINESS: one place that assembles the agent, so the live site, the tests and the
  golden-question evaluation all run exactly the same engine.
TECH: reads content/glossary.json (lookup_term), content/desk-questions.json (chip
  labels for the offline answers) and content/ask-the-tape.json (offline words and
  notices). providers can be injected (tests pass a FakeProvider as "anthropic").
  From Step 5c the agent's copy is a tape_db.AgentTape: contributions say how each
  stage adds its columns (main.py passes Product Slotting's), and the tools follow
  the stages the copy holds. With no contributions the agent knows the tape only.
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
from app.agent.tape_db import AgentTape, Contribution
from app.agent.tools import TapeTools
from app.loan_query import ColumnTypes
from app.slotting import SlottingRules

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
    tape: AgentTape
    tools: TapeTools


def build_ask_service(parquet_path: Path, columns: ColumnTypes, labels: dict[str, str],
                      desk_where: dict[str, str],
                      summarize: Callable[[], tuple[dict[str, Any], str]],
                      cfg: AgentConfig | None = None,
                      providers: dict[str, LLMProvider] | None = None,
                      base_columns: list[str] | None = None,
                      contributions: dict[str, Contribution] | None = None,
                      grid_columns: Callable[[], ColumnTypes] | None = None,
                      slotting: tuple[SlottingRules, dict[str, Any]] | None = None) -> AskService:
    """Build the agent for one tape.

    TECH: desk_where is desk question id -> validated SQL rule (desk_questions.py).
      base_columns are the default columns every loan-level result shows
      (api.toml [columns], via main.default_columns); None or [] adds none.
      Injected providers replace the vendor adapters by name; offline is always
      LoanIQ's own. contributions: stage id -> how it adds its columns to the copy;
      grid_columns: the Loan Tape's columns now ("Open in Loan Tape" links);
      slotting: (rules, words) for the explain_slot tool. columns is kept for the
      callers' signature; the tools read their columns from the copy.
    """
    cfg = cfg or load_agent_config()
    words = read_json("ask-the-tape.json")
    chip_labels = {q["id"]: q["label"] for q in read_json("desk-questions.json")["questions"]}
    offline = OfflineProvider(cfg.offline_rules, desk_where, chip_labels, words["offline"])
    tape = AgentTape(parquet_path, contributions or {})
    store = QueryStore(cfg.limits.query_store_size, cfg.limits.query_store_ttl_s)
    tools = TapeTools(tape, None, labels, read_json("glossary.json"), summarize, store, cfg.limits,
                      base_columns or [], grid_columns=grid_columns, slotting=slotting)
    meter = SpendMeter(cfg.budget)
    all_providers = {**build_providers(cfg, offline), **(providers or {}), "offline": offline}
    orchestrator = Orchestrator(cfg, all_providers, offline, tools, meter, words["notices"])
    return AskService(cfg=cfg, orchestrator=orchestrator, store=store, meter=meter, tape=tape,
                      tools=tools)


def close_ask_service(service: AskService) -> None:
    """Close the read-only tape and delete its temporary file.

    TECH: waits for a rebuild in progress first (tape_db.AgentTape.close).
    """
    service.tape.close()
