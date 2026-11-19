"""The Loan Tape screen's panels: program mix, note-rate buckets, delinquency and chips.

Where it sits:
    DuckDB table `loans` (main.py) -> [tape_panels] -> /api/tape, /api/loans/breakdowns,
    /api/loans/questions -> the three summary panels, the title line and the
    desk-question chips on the Loan Tape screen

BUSINESS:
    Before the grid, a trader wants the shape of the tape at a glance:
      - Program mix: how much balance is Conventional, Jumbo, FHA, Non-QM ... which
        decides who can buy the loans (GSEs, Ginnie Mae, private investors).
      - Note-rate distribution: current UPB in half-point buckets. The WAC is one
        number; two clusters of coupons (say 3-4.5% and 6-7%) average to a WAC no
        loan actually has, and they go into very different TBA coupons.
      - MBA delinquency: loans by status. Anything but Current prices lower and
        usually cannot be pooled.
      - Desk questions: how many loans answer each one-click question (LTV over 125,
        New York, ...), defined in config/desk_questions.toml.
    Every number covers the whole tape, not the grid's current filter (the same
    choice as the KPI tiles, docs/decisions.md). All numbers are illustrative,
    because the tape is synthetic.

TECH:
    Each panel is one GROUP BY (or one FILTER aggregate) over the in-memory table, so
    a 50,000-loan tape answers in a few milliseconds. Every value from config (bucket
    edges) goes in as a `?` parameter. The desk-question rules are SQL text, but only
    the validated, re-rendered SQL from app/desk_questions.py is used: it comes from
    the config file, never from the browser. Sums of current_upb stay exact DECIMAL
    in DuckDB and become float only for JSON (docs/decisions.md, "Money returned as
    JSON numbers"). Settings live in config/api.toml [breakdowns].
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping, Sequence

import duckdb
from pydantic import BaseModel

from app.desk_questions import DeskQuestion


# =============================================================================
# Response models
# =============================================================================

class ProgramSlice(BaseModel):
    """One bar of the Program mix panel.

    BUSINESS: "Conventional: 812 loans, $212.8M current UPB".
    TECH: current_upb in dollars (sum over the program's loans).
    """
    program: str
    loans: int
    current_upb: float


class RateBucket(BaseModel):
    """One bar of the Note rate distribution panel.

    BUSINESS: "6.0-6.5%: 312 loans, $114.9M". The first bucket also holds any lower
      rate and the last any higher one, so no loan is left out.
    TECH: low and high in percent; low is included, high excluded. low is null on the
      first bucket (open below) and high is null on the last (open above).
    """
    low: float | None
    high: float | None
    loans: int
    current_upb: float


class StatusCount(BaseModel):
    """One line of the MBA delinquency panel.

    BUSINESS: "60 days past due: 21 loans". TECH: current_upb in dollars.
    """
    status: str
    loans: int
    current_upb: float


class Breakdowns(BaseModel):
    """GET /api/loans/breakdowns: the three summary panels, whole tape.

    TECH: programs largest balance first; note_rates in rate order, every bucket
      present (0 when empty); dq_status in the config order, then any status the
      config does not list.
    """
    programs: list[ProgramSlice]
    note_rates: list[RateBucket]
    dq_status: list[StatusCount]


class QuestionCount(BaseModel):
    """One desk-question chip: how many loans answer it.

    BUSINESS: "LTV over 125: 20 loans". TECH: id matches config/desk_questions.toml
      and content/desk-questions.json (the label); current_upb in dollars.
    """
    id: str
    loans: int
    current_upb: float


class TapeInfo(BaseModel):
    """GET /api/tape: the line under the screen title.

    BUSINESS: "Seller tape · 41 fields · 6 fictional sellers".
    TECH: fields is the number of tape columns; sellers counts distinct seller names.
    """
    loans: int
    fields: int
    sellers: int


# =============================================================================
# Note-rate buckets
# =============================================================================

@dataclass(frozen=True)
class BucketSpec:
    """The note-rate bucket edges from api.toml [breakdowns], in percent.

    BUSINESS: half-point buckets from 2.0% to "9.0% and up" (illustrative).
    TECH: buckets are numbered 0 .. count-1. Bucket i covers
      [first_low + i x width, first_low + (i+1) x width), except that bucket 0 is
      open below and the last bucket (which starts at last_low) is open above.
    """
    width: float
    first_low: float
    last_low: float

    @property
    def count(self) -> int:
        """Number of buckets, the open-ended last one included."""
        return round((self.last_low - self.first_low) / self.width) + 1

    def edges(self, index: int) -> tuple[float | None, float | None]:
        """(low, high) of bucket `index` in percent; None marks an open end."""
        low = None if index == 0 else round(self.first_low + index * self.width, 6)
        high = None if index == self.count - 1 else round(self.first_low + (index + 1) * self.width, 6)
        return low, high


def bucket_spec(cfg: Mapping[str, Any]) -> BucketSpec:
    """Read and check the bucket settings from api.toml [breakdowns].

    BUSINESS: a typo in the config (a zero width, a last bucket below the first) must
      stop start-up rather than draw a misleading chart.
    TECH: (last - first) must be a whole number of widths, to within rounding.
    """
    spec = BucketSpec(width=float(cfg["note_rate_bucket_width"]),
                      first_low=float(cfg["note_rate_first_bucket_low"]),
                      last_low=float(cfg["note_rate_last_bucket_low"]))
    steps = (spec.last_low - spec.first_low) / spec.width if spec.width > 0 else -1
    if spec.width <= 0 or steps < 1 or abs(steps - round(steps)) > 1e-9:
        raise ValueError("api.toml [breakdowns]: note-rate buckets need width > 0 and "
                         "last_low - first_low a whole number (>= 1) of widths")
    return spec


# BUSINESS: bucket number = how many half points the rate is above the first edge,
#   clamped so lower rates land in the first bucket and higher ones in the last:
#     bucket = min(max(floor((note_rate - first_low) / width), 0), count - 1)
# TECH: ROUND(..., 9) before FLOOR removes float noise, so a rate exactly on an edge
#   (6.000 with width 0.5) is never read as 5.999999 and put one bucket too low.
#   Every edge value is a `?` parameter. Rates are never null on the tape; the WHERE
#   guards a future tape where they might be.
RATE_BUCKET_SQL = """
SELECT LEAST(GREATEST(CAST(FLOOR(ROUND((note_rate - ?) / ?, 9)) AS INTEGER), 0), ?) AS bucket,
       COUNT(*) AS loans,
       COALESCE(SUM(current_upb), 0) AS upb
FROM loans
WHERE note_rate IS NOT NULL
GROUP BY bucket
"""


def rate_buckets(cur: duckdb.DuckDBPyConnection, spec: BucketSpec) -> list[RateBucket]:
    """Current UPB and loan count per note-rate bucket, every bucket present.

    TECH: empty buckets are filled with zeros in Python, so the chart always has the
      same bars in the same places and a gap in the coupons is visible as a gap.
    """
    params = [spec.first_low, spec.width, spec.count - 1]
    found = {b: (n, upb) for b, n, upb in cur.execute(RATE_BUCKET_SQL, params).fetchall()}
    out = []
    for i in range(spec.count):
        low, high = spec.edges(i)
        loans, upb = found.get(i, (0, Decimal(0)))
        out.append(RateBucket(low=low, high=high, loans=loans, current_upb=float(upb)))
    return out


# =============================================================================
# Program mix and delinquency
# =============================================================================

# BUSINESS: largest program first, the way the panel reads. TECH: program breaks ties
#   so the order is stable.
PROGRAM_SQL = """
SELECT program, COUNT(*) AS loans, COALESCE(SUM(current_upb), 0) AS upb
FROM loans GROUP BY program ORDER BY upb DESC, program
"""

STATUS_SQL = "SELECT dq_status, COUNT(*), COALESCE(SUM(current_upb), 0) FROM loans GROUP BY dq_status"


def programs(cur: duckdb.DuckDBPyConnection) -> list[ProgramSlice]:
    """Loans and current UPB by program, largest UPB first."""
    return [ProgramSlice(program=p, loans=n, current_upb=float(upb))
            for p, n, upb in cur.execute(PROGRAM_SQL).fetchall()]


def statuses(cur: duckdb.DuckDBPyConnection, order: Sequence[str]) -> list[StatusCount]:
    """Loans and current UPB by MBA status, in the config's order.

    BUSINESS: every status the desk tracks shows, even with 0 loans, so "no REO" is
      visible rather than a missing line.
    TECH: statuses on the tape but missing from `order` follow, alphabetically, so no
      loan is ever hidden from the panel by a config gap.
    """
    found = {s: (n, upb) for s, n, upb in cur.execute(STATUS_SQL).fetchall()}
    names = list(order) + sorted(s for s in found if s not in order and s is not None)
    return [StatusCount(status=s, loans=found.get(s, (0, 0))[0],
                        current_upb=float(found.get(s, (0, Decimal(0)))[1]))
            for s in names]


def fetch_breakdowns(con: duckdb.DuckDBPyConnection, spec: BucketSpec,
                     dq_order: Sequence[str]) -> Breakdowns:
    """All three panels for the whole tape.

    TECH: three small GROUP BY queries on one per-request cursor (a cursor is a
      separate query state over the same database, so requests never share one).
    """
    cur = con.cursor()
    try:
        return Breakdowns(programs=programs(cur), note_rates=rate_buckets(cur, spec),
                          dq_status=statuses(cur, dq_order))
    finally:
        cur.close()


# =============================================================================
# Desk-question counts and the tape line
# =============================================================================

def question_counts_sql(questions: Sequence[DeskQuestion]) -> str:
    """One SELECT that counts every desk question in a single pass over the tape.

    BUSINESS: all chip counts at once, so they always describe the same tape.
    TECH: COUNT(*) FILTER (WHERE rule) counts only the rows where the rule is true.
      The rules are the validated SQL from app/desk_questions.py (config only; the
      browser never sends SQL), so placing them in the text is safe. With no
      questions the query is a harmless SELECT 1.
    """
    parts = []
    for q in questions:
        parts.append(f"COUNT(*) FILTER (WHERE {q.where})")
        parts.append(f"COALESCE(SUM(current_upb) FILTER (WHERE {q.where}), 0)")
    return f"SELECT {', '.join(parts) or '1'} FROM loans"


def fetch_question_counts(con: duckdb.DuckDBPyConnection,
                          questions: Sequence[DeskQuestion]) -> list[QuestionCount]:
    """Loans and current UPB answering each desk question, in config order."""
    if not questions:
        return []
    cur = con.cursor()
    try:
        row = cur.execute(question_counts_sql(questions)).fetchone()
    finally:
        cur.close()
    # TECH: the row holds (count, upb) pairs in question order.
    return [QuestionCount(id=q.id, loans=row[2 * i], current_upb=float(row[2 * i + 1]))
            for i, q in enumerate(questions)]


def fetch_tape_info(con: duckdb.DuckDBPyConnection, field_count: int) -> TapeInfo:
    """Loan count, field count and the number of distinct sellers.

    BUSINESS: "41 fields · 6 fictional sellers" tells the visitor how wide the tape
      is and how many companies are offering loans in it.
    TECH: COUNT(DISTINCT seller) ignores nulls; an empty tape gives 0 sellers.
    """
    cur = con.cursor()
    try:
        loans, sellers = cur.execute("SELECT COUNT(*), COUNT(DISTINCT seller) FROM loans").fetchone()
    finally:
        cur.close()
    return TapeInfo(loans=loans, fields=field_count, sellers=sellers)
