"""Tests for the Ask the Tape API, the golden questions and the eval script.

BUSINESS: what the screen (Step 4b) will rely on: POST /api/ask streams each step
  (tool calls with their SQL, the answer, query ids, cost) as Server-Sent Events;
  GET /api/ask/queries/{id} returns every row behind an answer; bad requests are
  refused before anything runs; one visitor's limit holds over HTTP. And the
  release gate: every golden question answered correctly on the Fake in CI.
TECH: FastAPI's TestClient over create_app with a FakeProvider as "anthropic".
  SSE responses are parsed from the raw text ("event: x" / "data: {...}" blocks
  separated by blank lines).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
# TECH: dataclasses.replace copies a frozen GoldenResult with some fields changed.
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import main
from app.agent.config import load_agent_config
from app.agent.golden import (GoldenQuestion, fake_script, grade, load_golden, numbers_in,
                              run_golden, truth)
from app.agent.providers.fake_provider import FakeProvider, text_turn
from scripts import eval_agent
from tests.agent_fixtures import (agent_cfg, loan_store, make_service, tape_dir,  # noqa: F401
                                  with_budget, with_limits)


def sse(text: str) -> list[tuple[str, Any]]:
    """Parse an SSE body into (event, data) pairs. TECH: data is JSON on every event."""
    out = []
    for block in text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        out.append((fields["event"], json.loads(fields["data"])))
    return out


@pytest.fixture()
def fake() -> FakeProvider:
    """The scripted model; tests set fake.steps."""
    return FakeProvider()


@pytest.fixture()
def client(tape_dir: Path, fake: FakeProvider) -> Iterator[TestClient]:  # noqa: F811
    """The whole app over the seeded tape, with the Fake as the live model."""
    with TestClient(main.create_app(tape_dir, ask_providers={"anthropic": fake})) as c:
        yield c


# =============================================================================
# POST /api/ask
# =============================================================================

def test_ask_streams_tool_calls_sql_answer_and_cost(client: TestClient, fake: FakeProvider) -> None:
    """BUSINESS: the visitor watches the agent work: the query and its SQL, the
    answer, then what it cost."""
    fake.steps = [eval_agent.fake_script(load_golden()[4])[0], text_turn("20 loans are over 125 LTV.")]
    r = client.post("/api/ask", json={"question": "How many loans have an LTV over 125?"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = sse(r.text)
    assert [e for e, _ in events] == ["tool_call", "tool_result", "answer", "done"]
    assert "ltv > 125" in events[1][1]["sql"] and events[2][1]["text"] == "20 loans are over 125 LTV."
    assert Decimal(events[3][1]["cost_usd"]) > 0


def test_desk_question_chip_and_its_rows(client: TestClient, loan_store: main.LoanStore) -> None:  # noqa: F811
    """BUSINESS: a chip answers with no model, and the screen can fetch every loan
    behind the answer: the same loans the grid's chip filter shows."""
    events = sse(client.post("/api/ask", json={"desk_question": "ltv_over_125"}).text)
    answer = next(d for e, d in events if e == "answer")
    count = loan_store.con.execute("SELECT COUNT(*) FROM loans WHERE ltv > 125").fetchone()[0]
    assert answer["text"].startswith(f"LTV over 125: {count} loans") and answer["provider"] == "offline"
    listing_id = next(d for e, d in events if e == "done")["query_ids"][1]
    rows = client.get(f"/api/ask/queries/{listing_id}").json()
    assert rows["row_count"] == count == len(rows["rows"]) and rows["columns"][0] == "loan_id"
    grid = client.get("/api/loans", params={"question": "ltv_over_125", "limit": 500}).json()
    assert {r[0] for r in rows["rows"]} == {r["loan_id"] for r in grid["rows"]}


@pytest.mark.parametrize("body, message", [
    ({"question": "   "}, "Ask a question"),
    ({"question": "x" * 501}, "limited to 500"),
    ({"desk_question": "no_such_chip"}, "Unknown desk question"),
])
def test_bad_requests_are_refused_before_streaming(client: TestClient, fake: FakeProvider,
                                                   body: dict, message: str) -> None:
    """BUSINESS: an empty, overlong or unknown question is a plain error, and the
    model is never called."""
    r = client.post("/api/ask", json=body)
    assert r.status_code == 400 and message in r.json()["detail"] and fake.calls == []


def test_unknown_query_id_is_404(client: TestClient) -> None:
    """TECH: an expired or made-up id is "not found", never another visitor's rows."""
    assert client.get("/api/ask/queries/q_nope").status_code == 404


def test_visitor_limit_over_http(tape_dir: Path, agent_cfg: Any) -> None:  # noqa: F811
    """BUSINESS: the per-visitor limit follows the address Render's proxy adds (the
    last X-Forwarded-For entry), not what the visitor types in front of it."""
    cfg = with_budget(agent_cfg, questions_per_visitor_per_day=1)
    fake = FakeProvider([text_turn("one"), text_turn("two")])
    with TestClient(main.create_app(tape_dir, agent_config=cfg, ask_providers={"anthropic": fake})) as c:
        def ask(xff: str) -> str:
            events = sse(c.post("/api/ask", json={"question": "Summarize the tape"},
                                headers={"X-Forwarded-For": xff}).text)
            return next(d for e, d in events if e == "done")["fallback_reason"] or "model"
        assert ask("1.1.1.1, 7.7.7.7") == "model"
        assert ask("2.2.2.2, 7.7.7.7") == "visitor_limit"
        assert ask("8.8.8.8") == "model"


def test_ask_routes_are_in_the_openapi_spec(client: TestClient) -> None:
    """TECH: the screen's TypeScript types are generated from this spec (npm run gen:api)."""
    paths = client.get("/openapi.json").json()["paths"]
    assert "post" in paths["/api/ask"] and "get" in paths["/api/ask/queries/{query_id}"]


# =============================================================================
# Golden questions: the release gate
# =============================================================================

def test_every_golden_question_passes_on_the_fake(make_service: Any, loan_store: main.LoanStore) -> None:  # noqa: F811
    """BUSINESS: every golden question's answer contains the tape's true number.

    TECH: the Fake runs each question's reference SQL through the real guardrails
      and tools, then answers from the real result; truth_sql is computed
      separately on the grid's store. About 20 questions, as in content/agent.md.
    """
    service = make_service(providers={"anthropic": FakeProvider()})
    questions = load_golden()

    def ask(q: GoldenQuestion) -> Any:
        service.orchestrator.providers["anthropic"] = FakeProvider(fake_script(q))
        return service.orchestrator.ask(q.question, "golden")
    results = run_golden(ask, questions, loan_store.con)
    failed = [(r.id, r.expected, r.answer) for r in results if not r.passed]
    assert 18 <= len(results) <= 25 and failed == []
    assert all(r.fallback_reason is None and r.provider == "fake" for r in results)


def test_golden_truth_is_computed_from_the_tape(loan_store: main.LoanStore) -> None:  # noqa: F811
    """BUSINESS: answers are not hard-coded; they follow the tape."""
    q = next(q for q in load_golden() if q.id == "loan_count")
    assert truth(loan_store.con, q) == 2000


@pytest.mark.parametrize("answer, expected, check, ok", [
    ("Total current UPB is $3.5M.", 3_512_345.67, "usd", True),
    ("Total current UPB is $4M.", 3_512_345.67, "usd", False),        # right digit, 14% off
    ("Total current UPB is $3.7M.", 3_512_345.67, "usd", False),      # two steps away
    ("About $3,512,345.67 in total", 3_512_345.67, "usd", True),
    ("3.51 million dollars", 3_512_345.67, "usd", True),
    ("The WAC is 6.41%.", 6.4123, "pct", True),
    ("The WAC is 6.5%.", 6.4123, "pct", False),
    ("There are 1,014 loans.", 1014, "count", True),
    ("There are 1,013 loans.", 1014, "count", False),
    ("WA FICO is 740.4", 740.3549, "number", True),
    ("The largest is ln16675948.", "LN16675948", "text", True),
    ("Loans took 5 months", 5_000_000, "usd", False),                  # "5 m..." is not $5M
    ("Nothing here", None, "count", False),
])
def test_grading_reads_numbers_the_way_a_desk_writes_them(answer: str, expected: Any,
                                                          check: str, ok: bool) -> None:
    """BUSINESS: a count must be exact; dollars and rates may be rounded the way a
    trader rounds them, but not further."""
    assert grade(answer, expected, check) is ok


def test_numbers_in_reads_scale_and_precision() -> None:
    """TECH: "$212.8M" is 212,800,000 written to the nearest 100,000 (10^5)."""
    assert list(numbers_in("$212.8M and 6.412%")) == [(Decimal("212.8E6"), -5), (Decimal("6.412"), 3)]


@pytest.mark.parametrize("toml, message", [
    ('[[question]]\nid="a"\nquestion="q"\ncheck="vibes"\ntruth_sql="SELECT 1"\nsql="SELECT 1"\nanswer="x"\n',
     "check must be"),
    ('[[question]]\nid="a"\nquestion="q"\ncheck="count"\ntruth_sql="SELECT 1"\nsql="SELECT 1"\nanswer="x"\n' * 2,
     "unique"),
])
def test_bad_golden_files_are_refused(tmp_path: Path, toml: str, message: str) -> None:
    """TECH: a typo in the golden file fails loudly instead of skipping a question."""
    path = tmp_path / "golden.toml"
    path.write_text(toml, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_golden(path)


# =============================================================================
# scripts/eval_agent.py
# =============================================================================

def test_eval_script_dry_run_reports_accuracy_tokens_and_cost(tape_dir: Path, tmp_path: Path,  # noqa: F811
                                                              capsys: pytest.CaptureFixture) -> None:
    """BUSINESS: the evaluation report a release decision reads: accuracy, tokens and
    cost per model. TECH: --fake runs it free, with no network."""
    out = tmp_path / "eval.json"
    code = eval_agent.main_cli(["--fake", "--data-dir", str(tape_dir), "--only", "wac", "loan_count",
                                "--models", "claude-haiku-5-5", "claude-sonnet-5-5", "--out", str(out)])
    printed = capsys.readouterr().out
    assert code == 0 and "Accuracy 2/2 (100.0%)" in printed and "per question" in printed
    report = json.loads(out.read_text(encoding="utf-8"))
    assert [m["model"] for m in report] == ["claude-haiku-5-5", "claude-sonnet-5-5"]
    assert report[1]["cost_usd"] > report[0]["cost_usd"], "Sonnet is priced above Haiku"


def test_eval_script_needs_a_key_for_live_runs(tape_dir: Path, monkeypatch: pytest.MonkeyPatch,  # noqa: F811
                                               capsys: pytest.CaptureFixture) -> None:
    """BUSINESS: a live run without a key stops at once, spending nothing."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert eval_agent.main_cli(["--data-dir", str(tape_dir), "--only", "wac"]) == 1
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().out


def fall_back(monkeypatch: pytest.MonkeyPatch, which: Any) -> None:
    """Make the chosen answers look like built-in-rule fallbacks after a rejected key.

    TECH: wraps the real run_model (the --fake run, no network) and rewrites the
      results that which(index) picks, with dataclasses.replace, the way a 401 from
      the live provider leaves them: provider "offline", fallback_reason "http_401".
    """
    real = eval_agent.run_model

    def run(*args: Any) -> list[Any]:
        return [replace(r, provider="offline", fallback_reason="http_401") if which(i) else r
                for i, r in enumerate(real(*args))]
    monkeypatch.setattr(eval_agent, "run_model", run)


def test_eval_script_fails_when_every_answer_falls_back(tape_dir: Path, tmp_path: Path,  # noqa: F811
                                                        monkeypatch: pytest.MonkeyPatch,
                                                        capsys: pytest.CaptureFixture) -> None:
    """BUSINESS: a run where the model never answered (a rejected key) measures the
    built-in rules, not the model. It must fail loudly with exit code 2, name the
    model and the reason, and leave the last good report on disk untouched."""
    fall_back(monkeypatch, lambda i: True)
    out = tmp_path / "eval.json"
    out.write_text("the last good report", encoding="utf-8")
    code = eval_agent.main_cli(["--fake", "--data-dir", str(tape_dir), "--only", "wac", "loan_count",
                                "--models", "claude-haiku-5-5", "claude-sonnet-5-5", "--out", str(out)])
    printed = capsys.readouterr().out
    assert code == 2
    assert "ERROR: all 2 answers on claude-haiku-5-5 came from built-in rules" in printed
    assert "http_401 x2" in printed and "No report was written." in printed
    assert "=== claude-sonnet-5-5 ===" not in printed, "the run stops at the first all-fallback model"
    assert out.read_text(encoding="utf-8") == "the last good report"


def test_eval_script_accepts_a_run_with_some_fallbacks(tape_dir: Path, tmp_path: Path,  # noqa: F811
                                                       monkeypatch: pytest.MonkeyPatch,
                                                       capsys: pytest.CaptureFixture) -> None:
    """BUSINESS: a few fallbacks (the --max-usd cap running out partway) are still a
    real measurement of the model: exit code 0, the report is written and counts them."""
    fall_back(monkeypatch, lambda i: i == 0)
    out = tmp_path / "eval.json"
    code = eval_agent.main_cli(["--fake", "--data-dir", str(tape_dir), "--only", "wac", "loan_count",
                                "--out", str(out)])
    assert code == 0 and "ERROR" not in capsys.readouterr().out
    assert json.loads(out.read_text(encoding="utf-8"))[0]["fallbacks"] == 1


def test_all_fallback_error_needs_every_answer_to_fall_back() -> None:
    """TECH: no results, or any answer from the model, is not an all-fallback run."""
    assert eval_agent.all_fallback_error("m", []) is None


def test_eval_config_sets_model_cap_and_escalation() -> None:
    """TECH: the run's model on tape_query, its own dollar cap, no visitor limit."""
    args = eval_agent.parse_args(["--max-usd", "0.10", "--no-escalate"])
    cfg = eval_agent.eval_config(load_agent_config(), "claude-sonnet-5-5", args)
    route = cfg.tasks["tape_query"]
    assert route.model == route.escalation_model == "claude-sonnet-5-5"
    assert cfg.budget.daily_cap_usd == Decimal("0.10") and cfg.budget.questions_per_visitor_per_day > 1000
