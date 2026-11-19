"""Desk questions: the one-click filters on the Loan Tape screen, loaded from config.

Where it sits:
    config/desk_questions.toml -> [desk_questions] -> loan API (main.py)
    -> /api/loans/questions (chip counts) and /api/loans?question=<id> (grid filter)

BUSINESS:
    A trader opening a new seller tape asks the same questions every time: how many
    loans are above 125 LTV, how many are in New York or Puerto Rico, how many are
    90+ days late or worse, modified, or in forbearance. Each question becomes a chip
    showing its loan count; clicking it filters the grid to exactly those loans.
    Keeping the rules in config means a new question is a config change, not a code
    change. All rules are illustrative; sources are in docs/public-sources.md.

TECH:
    Each rule's `where` is SQL, so it is treated as code, not trusted text. It is
    checked by spec_stories.validate_where, the same sqlglot allowlist the spec
    stories use (tape columns, comparisons, AND/OR/NOT, IN, BETWEEN, literals), and
    only sqlglot's re-rendering of the checked tree is kept. The browser never sends
    SQL: it sends a question id, which main.py looks up in the dict built here, so an
    unknown id is simply "not found" and nothing typed can reach the query text.
    Loading runs once when the API starts (it needs the tape's real column list);
    any bad entry stops start-up with an error naming the question.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from app.spec_stories import validate_where

DESK_QUESTIONS_PATH = Path(__file__).resolve().parent / "config" / "desk_questions.toml"

# TECH: the keys a [[question]] table may have, and the shape of an id. The id travels
#   in URLs (?question=ltv_over_125), so it is kept to plain lower-case characters.
QUESTION_KEYS = {"id", "where"}
ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,39}$")


@dataclass(frozen=True)
class DeskQuestion:
    """One desk question after validation.

    BUSINESS: "the loans for which `where` is true", for example ltv > 125.
    TECH: `where` is the validated, re-rendered DuckDB SQL, safe to place inside a
      WHERE clause. It holds no user input; it comes only from the config file.
    """

    id: str
    where: str


def check_question_entry(entry: dict[str, Any]) -> str:
    """Structural checks on one [[question]] table; returns its id.

    BUSINESS: catches typos (a missing rule, an id with spaces) at start-up, not when
      a trader clicks the chip.
    TECH: raises ValueError with the question's id (or "<unnamed>") in the message.
    """
    qid = entry.get("id", "<unnamed>")
    unknown, missing = set(entry) - QUESTION_KEYS, QUESTION_KEYS - set(entry)
    if unknown or missing:
        raise ValueError(f"Desk question {qid}: unknown keys {sorted(unknown)}, "
                         f"missing {sorted(missing)}")
    if not isinstance(qid, str) or not ID_PATTERN.match(qid):
        raise ValueError(f"Desk question {qid!r}: id must be lower-case letters, digits "
                         f"and _, starting with a letter")
    if not isinstance(entry["where"], str):
        raise ValueError(f"Desk question {qid}: `where` must be text")
    return qid


def load_desk_questions(columns: Sequence[str],
                        path: Path = DESK_QUESTIONS_PATH) -> dict[str, DeskQuestion]:
    """Load and validate every desk question, in config order.

    BUSINESS: the single entry point; if any rule is unsafe or malformed, the API
      does not start, rather than showing a chip with a wrong count.
    TECH: `columns` is the tape's real column list (from DESCRIBE loans in main.py).
      Returns id -> DeskQuestion; Python dicts keep insertion order, so the chips
      appear in the order of the config file. Raises ValueError (UnsafeWhereError
      is a ValueError) on any problem, including a duplicate id.
    """
    with path.open("rb") as f:
        entries = tomllib.load(f).get("question", [])
    questions: dict[str, DeskQuestion] = {}
    for entry in entries:
        qid = check_question_entry(entry)
        if qid in questions:
            raise ValueError(f"Duplicate desk question id: {qid}")
        # TECH: the same allowlist check as the spec stories, labelled for this file.
        where = validate_where(entry["where"], columns, qid, kind="Desk question")
        questions[qid] = DeskQuestion(id=qid, where=where)
    return questions
