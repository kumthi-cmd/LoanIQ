"""The Ask the Tape routes: POST /api/ask (streamed) and GET /api/ask/queries/{id}.

Where it sits:
    screen (Step 4b) -> [POST /api/ask] -> orchestrator events -> SSE stream
    screen -> [GET /api/ask/queries/{id}] -> QueryStore -> every row of one result

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
  - An APIRouter is a group of routes that main.py adds to the app with
    include_router, keeping the agent's routes out of main.py.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.sse import EventSourceResponse, ServerSentEvent
from pydantic import BaseModel, Field

from app.agent.budget import visitor_key
from app.agent.query_store import StoredQuery
from app.agent.service import AskService

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
    host = request.client.host if request.client else None
    visitor = visitor_key(request.headers.get("x-forwarded-for"), host,
                          service.cfg.budget.trust_forwarded_for, service.meter.salt)
    return AskInput(question=question, desk_question=body.desk_question, visitor=visitor)


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
