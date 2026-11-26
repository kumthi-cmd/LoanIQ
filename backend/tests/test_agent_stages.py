"""Tests for Ask the Tape's stages (Step 5c): agent/stages.py, tape_db.AgentTape,
explain_slot and the stage-aware prompt, tools and status.

BUSINESS: protects "the agent's scope grows with the desk": on the bare tape it knows
  the tape, says Product Slotting has not run, and is not offered explain_slot; once
  the desk has run slotting it has the flat slot columns, the Slotting prompt section
  and explain_slot, with the same answers as the Loan Tape. A rebuild never breaks a
  question in flight, a failed rebuild keeps the agent working, and the SQL guard is
  as strict on the bigger copy as before (one table, no joins, no WITH).
TECH: pytest. AgentTape is built straight from the seeded tape with main.py's own
  contributions; the API cases go through TestClient. Concurrency is tested with real
  threads querying while the copy is rebuilt.
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient

from app import main
from app.agent import stages as st
from app.agent.providers.base import ToolCall
from app.agent.providers.fake_provider import FakeProvider, text_turn
from app.agent.sql_guard import GuardrailError, check_query
from app.agent.tape_db import AgentTape
from app.slotting import agent_column_names, load_slotting_words, story_column
from tests.agent_fixtures import loan_store, make_service, tape_dir  # noqa: F401

WORDS = load_slotting_words()


@pytest.fixture()
def agent_tape(tape_dir: Path, loan_store: main.LoanStore) -> Iterator[AgentTape]:  # noqa: F811
    """A fresh agent copy of the seeded tape, wired with main.py's stage contributions."""
    tape = AgentTape(tape_dir / main.TAPE_FILE, main.agent_contributions(loan_store.slotting, WORDS))
    yield tape
    tape.close()


# =============================================================================
# The stage registry and the prompt
# =============================================================================

def test_stages_follow_the_desks_order() -> None:
    """BUSINESS: tape -> slotting -> best execution -> optimization -> pooling -> trading;
      tape and slotting are built, the rest are planned."""
    assert st.STAGE_IDS == ("tape", "slotting", "bestex", "optimization", "pooling", "trading")
    assert [s.id for s in st.STAGES if s.built] == ["tape", "slotting"]
    states = {s.id: st.stage_state(s, frozenset({"tape"})) for s in st.STAGES}
    assert states == {"tape": "known", "slotting": "not_run", "bestex": "planned",
                      "optimization": "planned", "pooling": "planned", "trading": "planned"}


def test_prompt_grows_with_the_stages() -> None:
    """BUSINESS: on the bare tape the agent is told slotting has not run; once it has,
      it gets the Slotting section instead. Planned stages are always named as not built.
    TECH: the same set of stages gives the very same string (prompt caching)."""
    bare = st.system_prompt(frozenset({"tape"}))
    slotted = st.system_prompt(frozenset({"tape", "slotting"}))
    assert st.read_prompt("slotting.pending.md") in bare and st.read_prompt("slotting.md") not in bare
    assert st.read_prompt("slotting.md") in slotted and st.read_prompt("slotting.pending.md") not in slotted
    assert st.read_prompt("planned.md") in bare and st.read_prompt("planned.md") in slotted
    assert st.system_prompt(frozenset({"tape"})) is bare
    assert len(slotted) < 2 * len(bare)  # TECH: it is sent with every question: keep it short


def test_slotting_prompt_names_exactly_the_agents_slot_columns(loan_store: main.LoanStore) -> None:  # noqa: F811
    """BUSINESS: the prompt never tells the model about a column that does not exist,
      nor leaves one out, as stories are added to spec_stories.toml."""
    text = st.read_prompt("slotting.md")
    for column in agent_column_names(loan_store.slotting):
        assert column in text, column
    stories = set(re.findall(r"story_[a-z_]+[a-z]", text))
    assert stories == {story_column(f) for f in loan_store.slotting.families()}


# =============================================================================
# The agent's copy: built, rebuilt, swapped
# =============================================================================

def test_the_bare_copy_is_the_tape_and_a_stage_adds_its_columns(agent_tape: AgentTape,
                                                                 loan_store: main.LoanStore) -> None:  # noqa: F811
    """BUSINESS: the agent starts from the seller's tape, and learns Slotting's columns
      when the stage is added; every loan keeps its row."""
    assert agent_tape.stages == {"tape"}
    with agent_tape.lease() as snap:
        assert list(snap.columns) == main.gen.COLUMNS
    agent_tape.add_stage("slotting")
    with agent_tape.lease() as snap:
        assert agent_tape.stages == {"tape", "slotting"}
        assert list(snap.columns) == main.gen.COLUMNS + agent_column_names(loan_store.slotting)
        assert snap.con.execute("SELECT COUNT(*), COUNT(*) FILTER (WHERE deliverable) FROM loans").fetchone() == (2000, 1467)
        assert snap.columns["deliverable"] == "BOOLEAN" and snap.columns["llb_tier"] == "INTEGER"


def test_a_query_in_flight_finishes_on_the_old_copy(agent_tape: AgentTape) -> None:
    """BUSINESS: a rebuild never breaks a question already running.
    TECH: the old copy stays open while leased and its folder is deleted after."""
    with agent_tape.lease() as old:
        agent_tape.add_stage("slotting")
        assert old.retired and old.folder is not None and old.folder.exists()
        assert old.con.execute("SELECT COUNT(*) FROM loans").fetchone()[0] == 2000
        assert "deliverable" not in old.columns
    assert not old.folder.exists()
    with agent_tape.lease() as new:
        assert "deliverable" in new.columns and new is not old


def test_queries_keep_working_through_repeated_rebuilds(agent_tape: AgentTape) -> None:
    """BUSINESS: visitors asking questions while the desk reruns slotting see no errors.
    TECH: four threads query in a loop, each on its own cursor, while the copy is
      rebuilt five times."""
    errors: list[BaseException] = []
    stop = threading.Event()

    def ask() -> None:
        while not stop.is_set():
            try:
                # TECH: one cursor per query, as the tools do (tools.run_sql); a DuckDB
                #   connection refuses two calls at once from different threads.
                with agent_tape.lease() as snap:
                    cur = snap.con.cursor()
                    try:
                        assert cur.execute("SELECT COUNT(*) FROM loans").fetchone()[0] == 2000
                    finally:
                        cur.close()
            except BaseException as exc:  # noqa: BLE001 - every failure must be seen
                errors.append(exc)
    threads = [threading.Thread(target=ask) for _ in range(4)]
    for t in threads:
        t.start()
    for _ in range(5):
        agent_tape.rebuild(frozenset({"tape", "slotting"}))
    stop.set()
    for t in threads:
        t.join()
    assert errors == []


def test_a_failed_rebuild_keeps_the_agent_working(tape_dir: Path, caplog: pytest.LogCaptureFixture) -> None:  # noqa: F811
    """BUSINESS: if a stage's columns cannot be built, the agent keeps what it knew,
      and the failure is logged."""
    def broken(_con: Any) -> None:
        raise ValueError("bad stage")
    tape = AgentTape(tape_dir / main.TAPE_FILE, {"slotting": broken})
    try:
        tape.add_stage_async("slotting").join()
        assert tape.stages == {"tape"}
        with tape.lease() as snap:
            assert snap.con.execute("SELECT COUNT(*) FROM loans").fetchone()[0] == 2000
        assert "Rebuilding the agent's tape with stage slotting failed" in caplog.text
    finally:
        tape.close()


def test_slot_columns_may_not_clash_with_tape_columns(tape_dir: Path, loan_store: main.LoanStore) -> None:  # noqa: F811
    """TECH: a tape column named like a slot column stops the build, never shadows."""
    def clash(con: Any) -> None:
        con.execute("ALTER TABLE loans ADD COLUMN deliverable BOOLEAN")
        main.agent_contributions(loan_store.slotting, WORDS)["slotting"](con)
    with pytest.raises(ValueError, match="clash"):
        AgentTape(tape_dir / main.TAPE_FILE, {"slotting": clash}).add_stage("slotting")


def test_the_guard_is_as_strict_on_the_slotted_copy(agent_tape: AgentTape) -> None:
    """BUSINESS: the new columns add no new ways in: still one table, no joins, no WITH.
    TECH: check_query with the slotted copy's columns as the allowlist."""
    agent_tape.add_stage("slotting")
    with agent_tape.lease() as snap:
        cols = snap.columns
    assert check_query("SELECT COUNT(*) FROM loans WHERE story_ny AND deliverable", cols, 500, 4000)
    for sql in ["SELECT * FROM loans l JOIN loans m USING (loan_id)", "SELECT * FROM slots",
                "WITH x AS (SELECT * FROM loans) SELECT * FROM x", "SELECT * FROM _agent_slots",
                "SELECT unknown_col FROM loans"]:
        with pytest.raises(GuardrailError):
            check_query(sql, cols, 500, 4000)


# =============================================================================
# Tools and prompt at each stage, through the agent
# =============================================================================

def test_explain_slot_is_offered_only_after_slotting(make_service: Any) -> None:  # noqa: F811
    """BUSINESS: before the desk has run slotting the agent has no explain_slot, and is
      told slotting has not run; after, it has both the tool and the Slotting section.
    TECH: what the Fake model was sent on each question."""
    fake = FakeProvider([text_turn("Not yet."), text_turn("Now yes.")])
    service = make_service(providers={"anthropic": fake}, stages=True)
    list(service.orchestrator.ask("How many loans are slotted?", "v"))
    service.tape.add_stage("slotting")
    list(service.orchestrator.ask("How many loans are slotted?", "v"))
    before, after = fake.calls
    assert "explain_slot" not in [t.name for t in before.tools]
    assert "explain_slot" in [t.name for t in after.tools]
    assert st.read_prompt("slotting.pending.md") in before.system
    assert st.read_prompt("slotting.md") in after.system


def test_explain_slot_before_slotting_says_so(make_service: Any) -> None:  # noqa: F811
    """BUSINESS: a model that calls explain_slot too early gets a plain "not yet", which
      is not counted as a guardrail failure."""
    service = make_service(stages=True)
    out = service.tools.run(ToolCall("c1", "explain_slot", {"loan_id": "LN78265415"}))
    assert out.result.is_error and not out.rejected
    assert "not available yet" in out.result.content


@pytest.mark.parametrize("loan_id, expect", [
    ("LN78265415", ["UMBS 30Y 2.5 / 3.0", "down coupon 2.5, up coupon 3.0", "LLB 275K", "NY", "Low FICO",
                    "orig_upb <= 275000", "Generic TBA · UMBS 30Y 2.5"]),
    ("LN79962194", ["Not slotted (No TBA product)", "7/6 ARM has no fixed-rate TBA coupon"]),
])
def test_explain_slot_gives_the_loan_tapes_card(make_service: Any, loan_id: str, expect: list[str]) -> None:  # noqa: F811
    """BUSINESS: the agent explains a loan exactly as the hover card does: the board's
      loan at UMBS 2.5 / 3.0 with three stories, and the ARM that has no TBA coupon."""
    service = make_service(stages=True)
    service.tape.add_stage("slotting")
    out = service.tools.run(ToolCall("c1", "explain_slot", {"loan_id": loan_id}))
    assert not out.result.is_error, out.result.content
    for text in expect:
        assert text in out.result.content
    assert out.result.data["loan_id"] == loan_id and out.event["loan_id"] == loan_id


@pytest.mark.parametrize("loan_id, rejected", [("LN123", True), ("LN00000000", False)])
def test_explain_slot_refuses_bad_and_unknown_ids(make_service: Any, loan_id: str, rejected: bool) -> None:  # noqa: F811
    """TECH: a malformed id is a guardrail failure; an id not on the tape is not."""
    service = make_service(stages=True)
    service.tape.add_stage("slotting")
    out = service.tools.run(ToolCall("c1", "explain_slot", {"loan_id": loan_id}))
    assert out.result.is_error and out.rejected is rejected


def test_open_in_loan_tape_uses_only_the_grids_columns(make_service: Any) -> None:  # noqa: F811
    """BUSINESS: a filter on a column only the agent has (story_ny) cannot open in the
      Loan Tape, and says why; a filter on a tape column still opens.
    TECH: grid_columns is the Loan Tape's column list (here, the seller's tape)."""
    service = make_service(stages=True)
    service.tape.add_stage("slotting")
    service.tools.grid_columns = lambda: {c: t for c, t in service.tools.columns.items() if c in main.gen.COLUMNS}
    agent_only = service.tools.run_query("SELECT loan_id FROM loans WHERE story_ny", "NY story")
    assert agent_only.loan_tape is not None and agent_only.loan_tape.filter is None
    assert "story_ny" in (agent_only.loan_tape.reason or "")
    on_tape = service.tools.run_query("SELECT loan_id FROM loans WHERE state = 'NY'", "NY")
    assert on_tape.loan_tape is not None and on_tape.loan_tape.filter


def test_status_lists_the_stages_and_follows_a_run(tape_dir: Path) -> None:  # noqa: F811
    """BUSINESS: the screen's scope strip: slotting is "not run" until the desk runs
      it, then "known"; later stages are "planned"."""
    with TestClient(main.create_app(tape_dir)) as c:
        before = {s["id"]: s["state"] for s in c.get("/api/ask/status").json()["stages"]}
        assert before["tape"] == "known" and before["slotting"] == "not_run" and before["trading"] == "planned"
        c.post("/api/slotting/run")
        c.app.state.ask.tape.wait()
        after = {s["id"]: s["state"] for s in c.get("/api/ask/status").json()["stages"]}
        assert after["slotting"] == "known" and after["bestex"] == "planned"


def test_labels_cover_every_agent_column(loan_store: main.LoanStore) -> None:  # noqa: F811
    """BUSINESS: list_columns gives the model a readable label for every slot column."""
    labels = main.agent_labels({}, loan_store.slotting, WORDS)
    assert set(agent_column_names(loan_store.slotting)) <= set(labels)
    assert labels["story_ny"] == "Carries the NY spec story (TRUE/FALSE)"
    assert json.dumps(labels)  # TECH: plain strings only
