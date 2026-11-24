"""Golden questions: questions with known answers, and how an answer is graded.

Where it sits:
    backend/evals/golden_questions.toml -> [golden] -> tests/test_agent_golden.py (Fake, CI)
                                                    -> scripts/eval_agent.py (live models)

BUSINESS:
    "A set of golden questions with known answers must pass before a release"
    (content/agent.md). Each question's true answer is computed straight from the
    tape by its own truth_sql, independently of the agent, so the check is: did the
    answer the visitor reads contain the tape's real number?
TECH:
    - In CI the model is a FakeProvider scripted with a reference query (`sql`) and
      an answer written from the real tool result. That tests everything except the
      model: the guardrails accept a reasonable query, the tools compute the right
      number, the answer path and the grader work. scripts/eval_agent.py runs the
      same questions on live models and reports accuracy, tokens and cost.
    - Grading reads numbers out of the answer text the way a desk writes them
      ($212.8M, 1,014, 6.412%) and accepts a number if it is the true value
      correctly rounded to the precision the answer used (within half a step) AND
      within 5% of it. For a true $3,512,345.67: "$3.5M" passes (written to the
      nearest $0.1M, and 0.35% off); "$4M" fails (to the nearest $1M it is right,
      but it is 14% off); "$3.7M" fails. For a true WAC of 6.4123%, "6.41%" passes
      and "6.5%" fails.
"""

from __future__ import annotations

import re
import time
import tomllib
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb

from app.agent.orchestrator import Event
from app.agent.providers.base import ChatTurn, Message, ToolResults
from app.agent.providers.fake_provider import Step, text_turn, tool_turn
from app.agent.providers.offline_provider import fmt_usd

GOLDEN_PATH = Path(__file__).resolve().parents[2] / "evals" / "golden_questions.toml"
CHECKS = ("count", "usd", "pct", "number", "text")
MAX_RELATIVE_ERROR = Decimal("0.05")

# TECH: a number as a desk writes it: optional $, digits with commas, optional
#   decimals, optional scale word or % sign. Group 2 is the digits, group 3 the
#   suffix. (?![a-z]) stops "5 months" reading as 5 million.
NUMBER = re.compile(r"(\$)?\s?(-?\d[\d,]*(?:\.\d+)?)\s?(%|billion|million|thousand|bn|mm|[kmb])?(?![a-z])",
                    re.IGNORECASE)
SCALES = {"k": 3, "thousand": 3, "m": 6, "mm": 6, "million": 6, "b": 9, "bn": 9, "billion": 9}


@dataclass(frozen=True)
class GoldenQuestion:
    """One question with a known answer.

    TECH:
      check       count (whole number, exact), usd (dollars), pct (percent),
                  number (any decimal), text (a value that must appear: a loan id,
                  a state, a seller)
      truth_sql   computes the true answer: the first column of the first row
      sql         the reference query a good agent might write (used by the Fake)
      answer      the Fake's answer template; {value} is the reference result
    """
    id: str
    question: str
    check: str
    truth_sql: str
    sql: str
    answer: str


def load_golden(path: Path = GOLDEN_PATH) -> list[GoldenQuestion]:
    """Read and check the golden questions. TECH: raises ValueError on a bad entry."""
    with path.open("rb") as f:
        raw = tomllib.load(f)["question"]
    questions = [GoldenQuestion(**q) for q in raw]
    for q in questions:
        if q.check not in CHECKS:
            raise ValueError(f"Golden question {q.id}: check must be one of {CHECKS}")
    if len({q.id for q in questions}) != len(questions):
        raise ValueError("Golden question ids must be unique")
    return questions


def truth(con: duckdb.DuckDBPyConnection, q: GoldenQuestion) -> Any:
    """The true answer from the tape. TECH: truth_sql comes from the repo, not from users."""
    return con.execute(q.truth_sql).fetchone()[0]


def numbers_in(text: str) -> Iterator[tuple[Decimal, int]]:
    """Every number in an answer: (value in units, decimals written).

    TECH: "$212.8M" -> (212800000, 1 decimal at the million scale -> written to the
      nearest 100,000). The decimals returned are relative to units: 1 - 6 = -5,
      meaning "rounded to 10^5".
    """
    for m in NUMBER.finditer(text):
        digits = m.group(2).replace(",", "")
        suffix = (m.group(3) or "").lower()
        places = len(digits.split(".")[1]) if "." in digits else 0
        scale = SCALES.get(suffix, 0)
        yield Decimal(digits).scaleb(scale), places - scale


def close_enough(found: Decimal, places: int, expected: Decimal) -> bool:
    """True if found is expected correctly rounded to `places` decimals, and within 5%.

    TECH: "correctly rounded" means within half a step: 6.41 is right for 6.4123
      (0.0023 off, half a step is 0.005), 6.5 is not (0.088 off, half a step 0.05).
      Exactly half a step is allowed, so either rounding of a tie passes.
    """
    half_step = Decimal(1).scaleb(-places) / 2
    if abs(found - expected) > half_step:
        return False
    return expected == 0 or abs(found - expected) / abs(expected) < MAX_RELATIVE_ERROR


def grade(answer: str, expected: Any, check: str) -> bool:
    """Does the answer contain the expected value? (rules in the module header)

    BUSINESS: a count must be exact; dollars and percents may be rounded the way a
      trader rounds them.
    """
    if expected is None:
        return False
    if check == "text":
        return str(expected).lower() in answer.lower()
    target = Decimal(str(expected))
    for value, places in numbers_in(answer):
        if check == "count" and value == target:
            return True
        if check in ("usd", "pct", "number") and close_enough(value, places, target):
            return True
    return False


def format_value(value: Any, check: str) -> str:
    """How the Fake writes a reference result: like a trader would."""
    if check == "count":
        return f"{int(value):,}"
    if check == "usd":
        return fmt_usd(float(value))
    if check == "pct":
        return f"{float(value):.3f}%"
    if check == "number":
        return f"{float(value):.1f}"
    return str(value)


def fake_script(q: GoldenQuestion) -> list[Step]:
    """The Fake's two turns: run the reference query, then answer from its result.

    TECH: the second step is a function of the messages, so the answer uses the
      number the tool really returned, not one written into the test.
    """
    def answer(messages: list[Message]) -> ChatTurn:
        result = next(r for m in reversed(messages) if isinstance(m, ToolResults) for r in m.results)
        if result.is_error:
            return text_turn(f"Could not answer: {result.content}")
        first_row = result.data["rows"][0]
        return text_turn(q.answer.format(value=format_value(next(iter(first_row.values())), q.check)))
    return [tool_turn(("query_tape", {"title": q.id, "sql": q.sql})), answer]


@dataclass
class GoldenResult:
    """One question's outcome. TECH: cost_usd is a string with 6 decimals, as in "done"."""
    id: str
    passed: bool
    expected: Any
    answer: str
    provider: str
    rounds: int
    usage: dict[str, int]
    cost_usd: str
    fallback_reason: str | None
    elapsed_ms: int


def run_golden(ask: Callable[[GoldenQuestion], Iterator[Event]], questions: list[GoldenQuestion],
               con: duckdb.DuckDBPyConnection) -> list[GoldenResult]:
    """Ask every question, grade every answer.

    TECH: ask(q) returns the orchestrator's events for q; the caller decides which
      provider answers (Fake in CI, a live model in the eval script).
    """
    results = []
    for q in questions:
        started = time.monotonic()
        events = list(ask(q))
        answer = next(e.data for e in events if e.type == "answer")
        done = next(e.data for e in events if e.type == "done")
        expected = truth(con, q)
        results.append(GoldenResult(
            id=q.id, passed=grade(answer["text"], expected, q.check), expected=expected,
            answer=answer["text"], provider=done["provider"], rounds=done["rounds"],
            usage=done["usage"], cost_usd=done["cost_usd"], fallback_reason=done["fallback_reason"],
            elapsed_ms=round((time.monotonic() - started) * 1000)))
    return results
