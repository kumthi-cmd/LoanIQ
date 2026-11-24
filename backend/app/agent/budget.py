"""Cost and limits: what each question costs, the daily cap, the per-visitor limit.

Where it sits:
    POST /api/ask -> [SpendMeter.check] -> orchestrator -> [cost_usd, SpendMeter.record]

BUSINESS:
    LoanIQ is a public showcase paying for its own model use, so spending must have
    a ceiling. Every question's tokens are priced (llm.toml [models], illustrative)
    and logged. Past the daily dollar cap, or past one visitor's daily question
    count, built-in rules answer and the screen says why. Desk-question chips never
    count: they skip the model entirely.

TECH:
    - Cost formula, dollars, Decimal throughout:
        cost = (input x input price + output x output price
                + cache_read x cache read price + cache_write x cache write price)
               / 1,000,000
      where each price is dollars per million tokens and input counts uncached
      tokens only (providers/base.Usage).
    - Spend and per-visitor counts live in memory and reset at UTC midnight. They
      also reset when the server restarts (on Render's free plan it sleeps after
      15 idle minutes), so the cap is a guard against runaway use, not an exact
      ledger. The provider console's own spend limit is the hard backstop.
      Recorded in docs/decisions.md.
    - A visitor is a salted SHA-256 hash of their IP address: counted, never
      stored. The salt is random per process, so hashes mean nothing elsewhere.
"""

from __future__ import annotations

import hashlib
import secrets
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal

from app.agent.config import Budget, ModelPrice
from app.agent.providers.base import Usage

PER_MILLION = Decimal(1_000_000)


def cost_usd(usage: Usage, price: ModelPrice) -> Decimal:
    """The dollar cost of some tokens at one model's prices (formula in the header)."""
    total = (usage.input_tokens * price.input + usage.output_tokens * price.output
             + usage.cache_read_tokens * price.cache_read
             + usage.cache_write_tokens * price.cache_write)
    return total / PER_MILLION


def utc_today() -> str:
    """TECH: today's date in UTC as YYYY-MM-DD, the day the budget counts in."""
    return datetime.now(timezone.utc).date().isoformat()


def visitor_key(forwarded_for: str | None, client_host: str | None, trust_forwarded: bool,
                salt: str) -> str:
    """A visitor's anonymous key from the request's address.

    TECH: behind Render's proxy the real client is the LAST X-Forwarded-For entry
      (Render appends it; earlier entries are whatever the client sent). Without
      a trusted proxy, the socket's address. 16 hex characters of a salted hash.
    """
    ip = client_host or "unknown"
    if trust_forwarded and forwarded_for:
        ip = forwarded_for.split(",")[-1].strip() or ip
    return hashlib.sha256(f"{salt}:{ip}".encode()).hexdigest()[:16]


class SpendMeter:
    """Today's spend and question counts, with the limits from llm.toml [budget].

    TECH: thread-safe (FastAPI runs sync routes on a thread pool). today is
      injectable so tests can cross midnight.
    """

    def __init__(self, budget: Budget, today: Callable[[], str] = utc_today) -> None:
        self.budget, self.today = budget, today
        self.salt = secrets.token_hex(16)
        self._lock = threading.Lock()
        self._day = ""
        self.spent = Decimal(0)
        self.questions: dict[str, int] = {}

    def _roll(self) -> None:
        """TECH: start a fresh day when the UTC date changes. Call holding the lock."""
        day = self.today()
        if day != self._day:
            self._day, self.spent, self.questions = day, Decimal(0), {}

    def check(self, visitor: str) -> str | None:
        """None if the model may answer; else the reason built-in rules answer.

        BUSINESS: "daily_budget" once today's spend reaches the cap;
          "visitor_limit" once this visitor has asked their daily number.
        """
        with self._lock:
            self._roll()
            if self.spent >= self.budget.daily_cap_usd:
                return "daily_budget"
            if self.questions.get(visitor, 0) >= self.budget.questions_per_visitor_per_day:
                return "visitor_limit"
            return None

    def record(self, visitor: str, cost: Decimal) -> None:
        """Count one model-answered question and its cost."""
        with self._lock:
            self._roll()
            self.spent += cost
            self.questions[visitor] = self.questions.get(visitor, 0) + 1
