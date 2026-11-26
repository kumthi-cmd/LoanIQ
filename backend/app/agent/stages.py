"""The desk's stages, and what Ask the Tape knows at each one.

Where it sits:
    a stage publishes (today: a Product Slotting run) -> agent/tape_db.AgentTape rebuilds
    the agent's copy -> [stages] -> the system prompt, the tool list and the scope strip
    on the Ask the Tape screen (GET /api/ask/status)

BUSINESS:
    The desk works a tape in order: tape (parsing) -> slotting -> best execution ->
    optimization -> pooling -> trading. Ask the Tape's scope grows with it: it knows
    the tape from the start, and each later stage once the desk has run it, from the
    same results the Loan Tape shows. Before a stage has run, the agent says so and
    points to it instead of guessing. Stages not built in LoanIQ yet are named, so
    the agent can say "not yet" plainly.
TECH:
    - STAGES is the one ordered list. A stage names its prompt section
      (agent/prompts/<id>.md, sent only once the stage is done), a one-line
      "not run yet" note (agent/prompts/<id>.pending.md, sent while it is not), and the
      tools it adds (offered to the model only once it is done).
    - The columns a stage adds to the agent's copy are built where its engine lives
      (slotting.agent_columns for Product Slotting) and registered in main.py; this
      module only knows ids and words, so it imports nothing from the engines.
    - The prompt is the base prompt plus those sections, in stage order. It changes
      only when a stage finishes, so it stays byte-for-byte the same between stage
      changes and prompt caching keeps working (orchestrator.py). It is cached per
      set of finished stages.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
BASE_PROMPT_PATH = Path(__file__).resolve().parent / "system_prompt.md"
TAPE = "tape"


@dataclass(frozen=True)
class Stage:
    """One stage of the desk's workflow.

    BUSINESS: built is False for a stage LoanIQ has not built yet (best execution and
      later), which the agent can only describe as coming.
    TECH: id names the prompt files; tools are tool names from tools.TOOL_SPECS.
    """
    id: str
    step: int
    built: bool
    tools: tuple[str, ...] = ()


# BUSINESS: the desk's order of work. Step numbers are the roadmap's (docs/roadmap.md).
STAGES: tuple[Stage, ...] = (
    Stage(TAPE, 1, built=True),
    Stage("slotting", 5, built=True, tools=("explain_slot",)),
    Stage("bestex", 6, built=False),
    Stage("optimization", 8, built=False),
    Stage("pooling", 8, built=False),
    Stage("trading", 7, built=False),
)
STAGE_IDS = tuple(s.id for s in STAGES)
# TECH: tool name -> the stage that offers it; tools not listed are always offered.
STAGE_OF_TOOL = {tool: s.id for s in STAGES for tool in s.tools}


def stage_state(stage: Stage, done: frozenset[str]) -> str:
    """BUSINESS: "known" (run), "not_run" (built, not run yet) or "planned" (not built)."""
    if stage.id in done:
        return "known"
    return "not_run" if stage.built else "planned"


def read_prompt(name: str) -> str:
    """One prompt file's text, without trailing blank lines."""
    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


@lru_cache(maxsize=16)
def system_prompt(done: frozenset[str], base: str | None = None) -> str:
    """The system prompt for a set of finished stages.

    BUSINESS: what the agent knows now: the base rules, a section per finished stage,
      a note per built stage that has not run, and one line naming the stages LoanIQ
      has not built yet.
    TECH: lru_cache keys on the frozenset, so each combination is assembled once.
      base defaults to system_prompt.md.
    """
    parts = [base if base is not None else BASE_PROMPT_PATH.read_text(encoding="utf-8").strip()]
    for stage in STAGES:
        state = stage_state(stage, done)
        if state == "known" and stage.id != TAPE:
            parts.append(read_prompt(f"{stage.id}.md"))
        elif state == "not_run":
            parts.append(read_prompt(f"{stage.id}.pending.md"))
    planned = [s.id for s in STAGES if not s.built]
    if planned:
        parts.append(read_prompt("planned.md"))
    return "\n\n".join(parts) + "\n"


def tool_allowed(tool: str, done: frozenset[str]) -> bool:
    """BUSINESS: a stage's tools are offered only once the stage has run."""
    stage = STAGE_OF_TOOL.get(tool)
    return stage is None or stage in done
