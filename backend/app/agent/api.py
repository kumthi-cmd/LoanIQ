"""The Ask the Tape routes: the question stream and what the screen needs around it.

Where it sits:
    screen (Step 4b) -> [POST /api/ask] -> orchestrator events -> SSE stream
    screen -> [GET /api/ask/queries/{id}] -> QueryStore -> every row of one result
    screen -> [GET /api/ask/status] -> is the model answering, or built-in rules?
    loan drawer -> [GET /api/ask/loans/{loan_id}] -> the agent's get_loan tool
    saved query -> [POST /api/ask/rerun] -> the agent's query_tape gate, no model

BUSINESS: the visitor sees the agent work step by step: each tool call with its
  SQL, then the answer, then what it cost. Then the screen fetches the full rows
  behind each query id.
TECH:
  - Server-Sent Events (SSE): one long HTTP response of "event: <type>" /
    "data: <json>" blocks, which the browser reads as they arrive. FastAPI 0.165
    has it built in: a route with response_class=EventSourceResponse that `yield`s
    ServerSentEvent objects. Event types: tool_call, tool_result, escalated,
    fallback, answer, done.
  - The body is checked in a dependency (ask_input) before streaming starts, so a
    bad request is a normal HTTP 400, not an error halfway through a stream.
  - Step 4b's routes reuse the agent's own tools (TapeTools), so the loan drawer
    and a saved-query rerun pass exactly the checks the model's calls pass, and
    never call a model or count against the AI budget.
  - An APIRouter is a group of routes that main.py adds to the app with
    include_router, keeping the agent's routes out of main.py.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, Field

from app.agent.budget import visitor_key
from app.agent.query_store import StoredQuery
from app.agent.service import AskService
from app.agent.tools import ToolFailure

router = APIRouter()


class AskRequest(BaseModel):
    """POST /api/ask body.

    BUSINESS: a typed question, or a desk-question chip's id (which skips the model).
    TECH: question length is checked against llm.toml max_question_chars in
      ask_input, so the limit lives in config.
    """
    question: str = Field("", description="The visitor's question, in plain English")
    desk_question: str | None = Field(None, description="A desk question id, e.g. ltv_over_125")


@dataclass(frozen=True)
class AskInput:
    """A checked request: the question text, the desk question id and the visitor key."""
    question: str
    desk_question: str | None
    visitor: str


def get_service(request: Request) -> AskService:
    """FastAPI dependency: the agent built at start-up (main.py lifespan)."""
    return request.app.state.ask


Service = Annotated[AskService, Depends(get_service)]


def ask_input(body: AskRequest, request: Request, service: Service) -> AskInput:
    """Check the body before the stream starts. TECH: HTTP 400 on a bad request.

    BUSINESS: an empty or overlong question, or an unknown chip id, is refused.
    """
    question = body.question.strip()
    limit = service.cfg.limits.max_question_chars
    if body.desk_question is not None:
        if body.desk_question not in service.orchestrator.offline.questions:
            raise HTTPException(400, f"Unknown desk question: {body.desk_question!r}")
    elif not question:
        raise HTTPException(400, "Ask a question about the loan tape.")
    if len(question) > limit:
        raise HTTPException(400, f"Questions are limited to {limit} characters.")
    return AskInput(question=question, desk_question=body.desk_question,
                    visitor=visitor_of(request, service))


def visitor_of(request: Request, service: AskService) -> str:
    """The visitor's salted key (budget.visitor_key): never the raw address."""
    host = request.client.host if request.client else None
    return visitor_key(request.headers.get("x-forwarded-for"), host,
                       service.cfg.budget.trust_forwarded_for, service.meter.salt)


@router.post("/api/ask", response_class=EventSourceResponse)
def ask(service: Service, checked: Annotated[AskInput, Depends(ask_input)]) -> Iterator[ServerSentEvent]:
    """BUSINESS: answer one question, streaming each step.

    TECH: a plain (sync) generator; FastAPI runs it on a worker thread, so the
      blocking model calls never stall other requests.
    """
    for event in service.orchestrator.ask(checked.question, checked.visitor, checked.desk_question):
        yield ServerSentEvent(event=event.type, data=event.data)


@router.get("/api/ask/queries/{query_id}", response_model=StoredQuery)
def query_result(query_id: str, service: Service) -> StoredQuery:
    """BUSINESS: every row behind one answer. TECH: 404 if unknown or expired (1 hour)."""
    stored = service.store.get(query_id)
    if stored is None:
        raise HTTPException(404, "Unknown or expired query id")
    return stored


# =============================================================================
# Step 4b: status, the loan drawer and saved-query reruns
# =============================================================================

class AskStatus(BaseModel):
    """Who answers this visitor's next typed question.

    BUSINESS: the screen shows a small banner when built-in rules ("Offline") are
      answering because the model is switched off or a daily limit is reached.
    TECH: mode "model" or "offline"; reason is the orchestrator's fallback code
      (unavailable, daily_budget, visitor_limit); notice is its visitor-facing words
      from content/ask-the-tape.json.
    """
    mode: str
    reason: str | None = None
    notice: str | None = None


@router.get("/api/ask/status", response_model=AskStatus)
def ask_status(request: Request, service: Service) -> AskStatus:
    """BUSINESS: is the AI model answering right now? TECH: no model call, no cost."""
    reason = service.orchestrator.status(visitor_of(request, service))
    if reason is None:
        return AskStatus(mode="model")
    return AskStatus(mode="offline", reason=reason, notice=service.orchestrator.notice(reason))


class LoanRecord(BaseModel):
    """One loan, every field. TECH: field name -> value (dates as ISO text)."""
    loan_id: str
    loan: dict[str, Any]


@router.get("/api/ask/loans/{loan_id}", response_model=LoanRecord)
def loan_record(loan_id: str, service: Service) -> LoanRecord:
    """BUSINESS: the loan drawer: click a loan id in an answer, see the whole loan.

    TECH: runs the agent's own get_loan tool (bound parameter, LN + 8 digits).
      400 for a malformed id, 404 for an id not on this tape.
    """
    try:
        _, data, extra = service.tools.get_loan({"loan_id": loan_id})
    except ToolFailure as exc:
        raise HTTPException(400 if exc.rejected else 404, str(exc)) from exc
    return LoanRecord(loan_id=extra["loan_id"], loan=data["loan"])


class RerunRequest(BaseModel):
    """POST /api/ask/rerun body: a saved query's SQL and its tag.

    TECH: the SQL's length is checked by sql_guard (llm.toml max_sql_chars).
    """
    sql: str = Field(..., description="The saved query's SQL, as the agent ran it")
    title: str = Field("Saved query", max_length=120, description="The saved query's tag")


@router.post("/api/ask/rerun", response_model=StoredQuery)
def rerun(body: RerunRequest, service: Service) -> StoredQuery:
    """BUSINESS: rerun a saved query on the tape without asking the model again.

    TECH: the SQL goes through the same sql_guard gate as the model's query_tape
      call (one SELECT, the loans table, known columns, bound values, row cap,
      timeout) and runs on the read-only tape. A refused query is a 400 with the
      guard's reason. No model call, so no cost and no visitor limit.
    """
    try:
        return service.tools.run_query(body.sql, body.title)
    except ToolFailure as exc:
        raise HTTPException(400, str(exc)) from exc
