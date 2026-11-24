"""The Offline provider: built-in rules that answer the desk questions with no model.

Where it sits:
    orchestrator -> [OfflineProvider.chat] -> tool calls through the same guardrails
    -> an answer from content/ask-the-tape.json templates

BUSINESS:
    The desk's everyday questions (LTV over 125, New York, 90+ / FC / REO / BK,
    modified, forbearance, a tape summary) need no AI at all. Built-in rules answer
    them when a visitor clicks a desk-question chip, when the AI is switched off,
    when today's budget is spent, or when the model fails. The answer still shows
    its SQL and its loans, because it goes through the same tools.

TECH:
    It implements the same LLMProvider interface, so the orchestrator runs it like
    any model: turn 1 returns tool calls, turn 2 writes the answer from the tool
    results (their structured `data`, not the CSV text). Rules come from
    llm.toml [[offline.rule]] (keywords -> desk question or summary); the desk
    question's SQL rule is the validated one from config/desk_questions.toml; the
    words are templates in content/ask-the-tape.json. No network, no tokens, free.
"""

from __future__ import annotations

from typing import Any

from app.agent.config import OfflineRule
from app.agent.providers.base import (ChatOptions, ChatTurn, LLMProvider, Message, ToolCall,
                                      ToolResult, ToolResults, ToolSpec, Usage, UserText)

# BUSINESS: the loans listed under a desk-question answer, largest balance first.
LIST_COLUMNS = "loan_id, seller, program, state, current_upb, note_rate, fico, ltv, dq_status"


def fmt_usd(value: float) -> str:
    """Dollars as a desk writes them: $212.8M, $412.5K, $812.34."""
    if abs(value) >= 1e9:
        return f"${value / 1e9:,.2f}B"
    if abs(value) >= 1e6:
        return f"${value / 1e6:,.1f}M"
    if abs(value) >= 1e3:
        return f"${value / 1e3:,.1f}K"
    return f"${value:,.2f}"


def fmt_pct(value: float | None, places: int) -> str:
    """A percent value (6.412 means 6.412%) with a % sign; a dash when missing."""
    return "-" if value is None else f"{value:.{places}f}%"


def match_rule(question: str, rules: tuple[OfflineRule, ...]) -> OfflineRule | None:
    """The first rule with a keyword in the question, or None.

    TECH: lower-cased and padded with spaces, so " ny" matches "in NY?" but not "any".
      Punctuation becomes a space for the same reason.
    """
    text = " " + "".join(ch if ch.isalnum() or ch in "+" else " " for ch in question.lower()) + " "
    for rule in rules:
        if any(k in text for k in rule.keywords):
            return rule
    return None


class OfflineProvider(LLMProvider):
    """Rule answers through the tools.

    TECH:
      rules       llm.toml [[offline.rule]], in order
      questions   desk question id -> validated SQL `where`
      labels      desk question id -> chip label (content/desk-questions.json)
      words       content/ask-the-tape.json "offline" templates
      pinned_rule a rule id to use regardless of the text (desk-question chips)
    """

    name = "offline"

    def __init__(self, rules: tuple[OfflineRule, ...], questions: dict[str, str],
                 labels: dict[str, str], words: dict[str, str], pinned_rule: str | None = None) -> None:
        self.rules, self.questions, self.labels, self.words = rules, questions, labels, words
        self.pinned_rule = pinned_rule

    def pinned(self, question_id: str) -> OfflineProvider:
        """A copy that answers one desk question, whatever the text says.

        TECH: a desk question with no keyword rule still works: one is made for it.
        """
        clone = OfflineProvider(self.rules, self.questions, self.labels, self.words, question_id)
        if not any(r.id == question_id for r in self.rules):
            clone.rules = self.rules + (OfflineRule("desk_question", question_id, ("\0",)),)
        return clone

    def rule_for(self, question: str) -> OfflineRule | None:
        """The rule that answers this question (the pinned one first)."""
        if self.pinned_rule:
            return next(r for r in self.rules if r.id == self.pinned_rule)
        return match_rule(question, self.rules)

    def chat(self, system: str, messages: list[Message], tools: list[ToolSpec],
             model: str, max_tokens: int, options: ChatOptions = ChatOptions()) -> ChatTurn:
        """Turn 1: the tool calls for the rule. Turn 2: the answer from their results."""
        question = next((m.text for m in messages if isinstance(m, UserText)), "")
        results = [r for m in messages if isinstance(m, ToolResults) for r in m.results]
        rule = self.rule_for(question)
        if rule is None:
            return ChatTurn(self.words["no_match"], [], Usage())
        if not results:
            return ChatTurn("", self.calls_for(rule), Usage(), stop_reason="tool_use")
        return ChatTurn(self.answer(rule, results), [], Usage())

    def calls_for(self, rule: OfflineRule) -> list[ToolCall]:
        """BUSINESS: totals for the question, then its loans. TECH: ids o1, o2."""
        if rule.kind == "summary":
            return [ToolCall("o1", "summarize_tape", {})]
        where, label = self.questions[rule.id], self.labels.get(rule.id, rule.id)
        # BUSINESS: WAC = SUM(note_rate x current_upb) / SUM(current_upb), percent.
        totals = ("SELECT COUNT(*) AS loans, SUM(current_upb) AS current_upb, "
                  "ROUND(SUM(note_rate * current_upb) / NULLIF(SUM(current_upb), 0), 3) AS wac "
                  f"FROM loans WHERE {where}")
        listing = f"SELECT {LIST_COLUMNS} FROM loans WHERE {where} ORDER BY current_upb DESC"
        return [ToolCall("o1", "query_tape", {"title": f"{label}: totals", "sql": totals}),
                ToolCall("o2", "query_tape", {"title": f"{label}: loans", "sql": listing})]

    def answer(self, rule: OfflineRule, results: list[ToolResult]) -> str:
        """Fill the rule's template from the first tool result's data."""
        first = results[0]
        if first.is_error:
            return f"{self.words['no_match']} ({first.content})"
        if rule.kind == "summary":
            s: dict[str, Any] = first.data
            return self.words["summary"].format(
                loans=f"{s['loan_count']:,}", upb=fmt_usd(s["total_current_upb"]),
                wac=fmt_pct(s["wac"], 3), fico=f"{s['wa_fico']:.0f}" if s["wa_fico"] else "-",
                ltv=fmt_pct(s["wa_ltv"], 1), delinquent=f"{s['delinquent_loans']:,}")
        row = first.data["rows"][0]
        label = self.labels.get(rule.id, rule.id)
        if not row["loans"]:
            return self.words["desk_question_empty"].format(label=label)
        return self.words["desk_question"].format(label=label, loans=f"{row['loans']:,}",
                                                  upb=fmt_usd(row["current_upb"]),
                                                  wac=fmt_pct(row["wac"], 3))
