"""Shared fixtures for the Ask the Tape tests (tests/test_agent_*.py).

BUSINESS: every agent test runs on the same seeded 2,000-loan tape the live site
  serves, so "20 loans over 125 LTV" in a test is the number a visitor would see.
TECH: pytest fixtures, imported by each agent test module with
  `from tests.agent_fixtures import *`-style named imports. Session scope: the tape
  is generated once per test run in a temp folder (the real data/ folder is never
  touched). make_service builds a full AskService (read-only tape, tools,
  orchestrator) with injectable providers and config, and closes it afterwards.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from app import loan_tape_gen as gen
from app import main
from app.agent.config import AgentConfig, load_agent_config
from app.agent.orchestrator import Event
from app.agent.providers.base import LLMProvider
from app.agent.service import AskService, build_ask_service, close_ask_service
from app.agent.tape_db import ReadOnlyTape, close_readonly_tape, open_readonly_tape
from app.slotting import load_slotting_words


@pytest.fixture(scope="session")
def tape_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A temp folder holding the default seeded tape (generator defaults)."""
    folder = tmp_path_factory.mktemp("agent_tape")
    gen.main(["--out-dir", str(folder)])
    return folder


@pytest.fixture(scope="session")
def loan_store(tape_dir: Path) -> Iterator[main.LoanStore]:
    """The grid's in-memory store over that tape: the independent source of truth."""
    store = main.open_store(tape_dir)
    yield store
    store.con.close()


@pytest.fixture(scope="session")
def ro_tape(tape_dir: Path) -> Iterator[ReadOnlyTape]:
    """The agent's read-only copy of the tape."""
    tape = open_readonly_tape(tape_dir / main.TAPE_FILE)
    yield tape
    close_readonly_tape(tape)


@pytest.fixture()
def agent_cfg() -> AgentConfig:
    """llm.toml as shipped."""
    return load_agent_config()


def with_limits(cfg: AgentConfig, **changes: Any) -> AgentConfig:
    """A copy of cfg with some [limits] changed, e.g. with_limits(cfg, max_rounds=2)."""
    return replace(cfg, limits=replace(cfg.limits, **changes))


def with_budget(cfg: AgentConfig, **changes: Any) -> AgentConfig:
    """A copy of cfg with some [budget] changed."""
    return replace(cfg, budget=replace(cfg.budget, **changes))


@pytest.fixture()
def make_service(tape_dir: Path, loan_store: main.LoanStore) -> Iterator[Callable[..., AskService]]:
    """Factory: make_service(providers={"anthropic": fake}, cfg=..., stages=True) -> AskService.

    TECH: stages=True wires the desk's stages as main.py does (Step 5c): Product
      Slotting's columns and explain_slot become available once the test calls
      service.tape.add_stage("slotting").
    """
    built: list[AskService] = []

    def make(providers: dict[str, LLMProvider] | None = None, cfg: AgentConfig | None = None,
             stages: bool = False) -> AskService:
        words = load_slotting_words()
        rules = loan_store.slotting
        service = build_ask_service(tape_dir / main.TAPE_FILE, loan_store.columns,
                                    main.agent_labels(main.load_labels(), rules, words),
                                    {k: q.where for k, q in loan_store.questions.items()},
                                    lambda: main.tape_summary(loan_store), cfg, providers,
                                    contributions=main.agent_contributions(rules, words) if stages else None,
                                    slotting=(rules, words) if stages and rules else None)
        built.append(service)
        return service
    yield make
    for service in built:
        close_ask_service(service)


def events_of(service: AskService, question: str, visitor: str = "v1",
              desk_question: str | None = None) -> list[Event]:
    """Run one question to the end and collect its events."""
    return list(service.orchestrator.ask(question, visitor, desk_question))


def one(events: list[Event], kind: str) -> dict[str, Any]:
    """The data of the single event of this type (fails if there is not exactly one)."""
    found = [e.data for e in events if e.type == kind]
    assert len(found) == 1, f"expected one {kind!r} event, got {len(found)}: {[e.type for e in events]}"
    return found[0]


def all_of(events: list[Event], kind: str) -> list[dict[str, Any]]:
    """The data of every event of this type, in order."""
    return [e.data for e in events if e.type == kind]
