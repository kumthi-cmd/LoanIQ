"""The query store: full query_tape results, kept by query id for the screen.

Where it sits:
    tools.query_tape -> [QueryStore.put] ... GET /api/ask/queries/{id} -> screen

BUSINESS: the model reads only totals and the first 20 rows; the visitor's screen
  shows every row of the same result (up to 500), so a trader can check the loans
  behind the answer.
TECH: an in-memory LRU ("least recently used") cache: an OrderedDict where the
  oldest entry is dropped once there are more than max_size, and entries older
  than ttl_s seconds expire. A lock makes it safe across FastAPI's worker threads.
  Ids are random (secrets.token_urlsafe), so one visitor cannot guess another's.
  Results are lost on restart; the screen then asks the question again.
"""

from __future__ import annotations

import secrets
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from app.agent.loan_tape_link import LoanTapeLink


class StoredQuery(BaseModel):
    """One query_tape result, as the screen gets it.

    BUSINESS: "Loans over 125 LTV: 20 rows" plus the SQL that produced them.
    TECH: rows are lists in `columns` order (smaller JSON than dicts). row_count
      is rows returned (at most max_rows); total_rows counts every row that
      matched; truncated is True when total_rows > row_count. loan_tape is how to
      open the result in the Loan Tape with the same filter (loan_tape_link.py,
      Step 4b); None only for results stored before it existed. added_columns
      names the default tape columns the server joined on for display (Step 4c,
      tools.add_base_columns); the model never sees them and the SQL does not
      select them.
    """
    query_id: str
    title: str
    sql: str
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    total_rows: int
    truncated: bool
    loan_tape: LoanTapeLink | None = None
    added_columns: list[str] = []


class QueryStore:
    """Thread-safe LRU of StoredQuery with expiry.

    TECH: clock is injectable so tests can move time forward.
    """

    def __init__(self, max_size: int, ttl_s: float,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.max_size, self.ttl_s, self.clock = max_size, ttl_s, clock
        self._items: OrderedDict[str, tuple[float, StoredQuery]] = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def new_id() -> str:
        """TECH: "q_" plus 12 random URL-safe characters (72 bits)."""
        return "q_" + secrets.token_urlsafe(9)

    def put(self, query: StoredQuery) -> None:
        """Store a result, dropping the oldest beyond max_size."""
        with self._lock:
            self._items[query.query_id] = (self.clock(), query)
            self._items.move_to_end(query.query_id)
            while len(self._items) > self.max_size:
                self._items.popitem(last=False)

    def get(self, query_id: str) -> StoredQuery | None:
        """A stored result, or None if unknown or expired."""
        with self._lock:
            item = self._items.get(query_id)
            if item is None:
                return None
            stored_at, query = item
            if self.clock() - stored_at > self.ttl_s:
                del self._items[query_id]
                return None
            self._items.move_to_end(query_id)
            return query
