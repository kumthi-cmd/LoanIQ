"""Tests for the Step 4b routes around Ask the Tape, and provider error logging.

BUSINESS: what the Ask the Tape screen relies on beyond the question stream:
  - GET  /api/ask/status        the Offline banner: is the model answering?
  - GET  /api/ask/loans/{id}    the loan drawer, through the agent's get_loan tool
  - POST /api/ask/rerun         a saved query reruns its SQL with no model call,
                                through the same guardrails as the model's SQL
  - each query result carries its "Open in Loan Tape" link
  And for the operator: a failed model call logs the provider's status and own
  message (never the API key or the visitor's question), so Render's logs say
  why Ask the Tape fell back.
TECH: FastAPI's TestClient over create_app with a FakeProvider as "anthropic";
  pytest's caplog fixture captures log lines.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import main
from app.agent.providers.base import (MAX_DETAIL_CHARS, ProviderError, redact, sdk_detail,
                                      sdk_error, sdk_reason, sdk_status)
from app.agent.providers.fake_provider import FakeProvider, text_turn, tool_turn
from app.agent.tools import TOOL_SPECS
from tests.agent_fixtures import agent_cfg, loan_store, tape_dir, with_budget  # noqa: F401
from tests.test_agent_api import sse


@pytest.fixture()
def fake() -> FakeProvider:
    """The scripted model; tests set fake.steps."""
    return FakeProvider()


@pytest.fixture()
def client(tape_dir: Path, fake: FakeProvider) -> Iterator[TestClient]:  # noqa: F811
    """The whole app over the seeded tape, with the Fake as the live model."""
    with TestClient(main.create_app(tape_dir, ask_providers={"anthropic": fake})) as c:
        yield c


LTV_SQL = "SELECT loan_id, ltv FROM loans WHERE ltv > 125 ORDER BY ltv DESC"


# =============================================================================
# GET /api/ask/status
# =============================================================================

def test_status_is_model_when_the_model_may_answer(client: TestClient, fake: FakeProvider) -> None:
    """BUSINESS: no banner while the AI model answers. TECH: asking costs no model call."""
    assert client.get("/api/ask/status").json() == {"mode": "model", "reason": None, "notice": None}
    assert fake.calls == []


def test_status_is_offline_without_a_key(tape_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    """BUSINESS: no ANTHROPIC_API_KEY on the server -> the banner says built-in rules answer."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with TestClient(main.create_app(tape_dir)) as c:
        status = c.get("/api/ask/status").json()
    assert status["mode"] == "offline" and status["reason"] == "unavailable"
    assert "switched off" in status["notice"]


def test_status_is_offline_once_the_visitor_limit_is_reached(tape_dir: Path, agent_cfg: Any) -> None:  # noqa: F811
    """BUSINESS: after today's questions are used, the banner appears before the next one."""
    cfg = with_budget(agent_cfg, questions_per_visitor_per_day=1)
    fake = FakeProvider([text_turn("one")])
    with TestClient(main.create_app(tape_dir, agent_config=cfg, ask_providers={"anthropic": fake})) as c:
        assert c.get("/api/ask/status").json()["mode"] == "model"
        c.post("/api/ask", json={"question": "How big is the tape?"})
        status = c.get("/api/ask/status").json()
    assert status["mode"] == "offline" and status["reason"] == "visitor_limit"


# =============================================================================
# GET /api/ask/loans/{loan_id}
# =============================================================================

def test_loan_drawer_returns_every_field(client: TestClient, loan_store: main.LoanStore) -> None:  # noqa: F811
    """BUSINESS: click a loan id, see the whole loan: every field of the tape."""
    loan_id = loan_store.con.execute("SELECT loan_id FROM loans ORDER BY loan_id LIMIT 1").fetchone()[0]
    r = client.get(f"/api/ask/loans/{loan_id.lower()}")
    assert r.status_code == 200
    body = r.json()
    assert body["loan_id"] == loan_id and set(body["loan"]) == set(loan_store.columns)


@pytest.mark.parametrize("loan_id, status", [("LN99999999", 404), ("1;DROP", 400), ("LN123", 400)])
def test_loan_drawer_refuses_bad_or_unknown_ids(client: TestClient, loan_id: str, status: int) -> None:
    """TECH: a malformed id never reaches DuckDB (400); a well-formed unknown one is 404."""
    assert client.get(f"/api/ask/loans/{loan_id}").status_code == status


# =============================================================================
# POST /api/ask/rerun and the Loan Tape link
# =============================================================================

def test_query_result_carries_its_loan_tape_link(client: TestClient, fake: FakeProvider) -> None:
    """BUSINESS: each answer's table can open in the Loan Tape with the same filter."""
    fake.steps = [tool_turn(("query_tape", {"sql": LTV_SQL, "title": "LTV > 125"})), text_turn("done")]
    events = sse(client.post("/api/ask", json={"question": "LTV over 125?"}).text)
    result = next(d for e, d in events if e == "tool_result")
    expected = {"filter": {"ltv": {"filterType": "number", "type": "greaterThan", "filter": 125}},
                "sort": "ltv:desc", "reason": None}
    assert result["loan_tape"] == expected
    assert client.get(f"/api/ask/queries/{result['query_id']}").json()["loan_tape"] == expected


def test_rerun_returns_the_same_rows_without_the_model(client: TestClient, fake: FakeProvider) -> None:
    """BUSINESS: a saved query reruns on the tape in one click, at no AI cost.
    TECH: the SQL saved is the display SQL the screen showed; rerunning it gives the
      same rows as the agent's run, and the model is never called."""
    fake.steps = [tool_turn(("query_tape", {"sql": LTV_SQL, "title": "LTV > 125"})), text_turn("done")]
    events = sse(client.post("/api/ask", json={"question": "LTV over 125?"}).text)
    first = client.get(f"/api/ask/queries/{next(d for e, d in events if e == 'tool_result')['query_id']}").json()
    calls = len(fake.calls)
    r = client.post("/api/ask/rerun", json={"sql": first["sql"], "title": "LTV > 125"})
    assert r.status_code == 200
    again = r.json()
    assert again["rows"] == first["rows"] and again["query_id"] != first["query_id"]
    assert again["loan_tape"] == first["loan_tape"] and len(fake.calls) == calls


@pytest.mark.parametrize("sql, words", [
    ("DELETE FROM loans", "Only SELECT"),
    ("SELECT * FROM read_csv('x.csv')", "Not allowed"),
    ("SELECT * FROM other_table", "Unknown table"),
    ("SELECT password FROM loans", "Unknown column"),
    ("SELECT 1; SELECT 2", "exactly one statement"),
])
def test_rerun_passes_the_same_guardrails(client: TestClient, sql: str, words: str) -> None:
    """BUSINESS: a rerun can do nothing the agent could not: SQL sent from the
    browser is checked by the same gate as the model's SQL."""
    r = client.post("/api/ask/rerun", json={"sql": sql})
    assert r.status_code == 400 and words in r.json()["detail"]


def test_screen_lists_exactly_the_agents_tools() -> None:
    """BUSINESS: the "Tools the agent can call" panel tells the truth: the same five
    tools, no more, no fewer (content/ask-the-tape.json vs tools.py)."""
    screen = json.loads((main.gen.REPO_ROOT / "content" / "ask-the-tape.json").read_text(encoding="utf-8"))["screen"]
    assert [t["name"] for t in screen["tools"]] == [t.name for t in TOOL_SPECS]


# =============================================================================
# Provider errors: the log says why, never the key or the question
# =============================================================================

class FakeSdkError(Exception):
    """Shaped like an SDK's HTTP error: status_code and a parsed JSON body."""

    def __init__(self, status: int, body: Any, message: str = "") -> None:
        super().__init__(message or f"Error code: {status}")
        self.status_code, self.body = status, body


def test_sdk_detail_reads_each_vendors_body() -> None:
    """TECH: Anthropic nests the message under "error"; OpenAI may not; else .message or str."""
    anthropic = FakeSdkError(400, {"type": "error", "error": {"type": "invalid_request_error",
                                                              "message": "model: not found"}})
    openai = FakeSdkError(401, {"message": "Incorrect API key provided"})
    bare = FakeSdkError(500, None, "upstream broke")
    assert sdk_detail(anthropic) == "model: not found"
    assert sdk_detail(openai) == "Incorrect API key provided"
    assert sdk_detail(bare) == "upstream broke"
    assert len(sdk_detail(FakeSdkError(400, {"message": "x" * 5000}))) == MAX_DETAIL_CHARS


def test_sdk_status_and_reason_read_gemini_code() -> None:
    """TECH: Gemini's errors carry .code, not .status_code."""
    exc = type("ClientError", (Exception,), {})()
    exc.code = 403
    assert sdk_status(exc) == 403 and sdk_reason(exc) == "http_403"


def test_redact_removes_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """BUSINESS: an API key must never reach a log, whatever shape it echoes back in."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "plain-secret-value-123")
    text = redact("key sk-ant-api03-abcdefghijklmnop and AIzaSyA1234567890123456789012 and "
                  "x-api-key: zzz and Authorization: Bearer tok123 and plain-secret-value-123")
    for secret in ("sk-ant-api03", "AIzaSy", "zzz", "tok123", "plain-secret-value-123"):
        assert secret not in text


def test_failed_call_logs_status_and_message_not_key_or_question(
        client: TestClient, fake: FakeProvider, caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch) -> None:
    """BUSINESS: Render's logs show "http_400: Your credit balance is too low", not
    just "http_400", and the visitor still gets an answer from built-in rules.
    TECH: the provider's message here even echoes the key and the question back;
      both must be gone from the log line."""
    key = "sk-ant-api03-secretsecretsecret"
    monkeypatch.setenv("ANTHROPIC_API_KEY", key)
    question = "Which NY loans are under 150K?"
    body = {"error": {"message": f"Your credit balance is too low (key {key}; prompt: {question})"}}
    fake.steps = [sdk_error(FakeSdkError(400, body), "Claude")]
    with caplog.at_level(logging.WARNING, logger="loaniq.ask"):
        events = sse(client.post("/api/ask", json={"question": question}).text)
    assert next(d for e, d in events if e == "fallback")["reason"] == "http_400"
    lines = [json.loads(r.getMessage()) for r in caplog.records if "provider_error" in r.getMessage()]
    assert len(lines) == 1
    line = lines[0]
    assert line["provider"] == fake.name and line["status"] == 400 and line["reason"] == "http_400"
    assert line["model"] and "credit balance is too low" in line["message"]
    assert key not in caplog.text and question not in caplog.text


def test_errors_without_detail_still_log_their_reason(client: TestClient, fake: FakeProvider,
                                                      caplog: pytest.LogCaptureFixture) -> None:
    """TECH: LoanIQ's own errors (no SDK body) log their message and no status."""
    fake.steps = [ProviderError("refusal", "Claude declined to answer this question")]
    with caplog.at_level(logging.WARNING, logger="loaniq.ask"):
        client.post("/api/ask", json={"question": "anything"})
    line = next(json.loads(r.getMessage()) for r in caplog.records if "provider_error" in r.getMessage())
    assert line["status"] is None and line["message"] == "Claude declined to answer this question"
