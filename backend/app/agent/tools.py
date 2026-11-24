"""The agent's tools: the only way the model can see the tape.

Where it sits:
    orchestrator -> [TapeTools.run] -> sql_guard + read-only DuckDB, glossary, summary
    -> ToolResult (for the model) + event (for the screen) + QueryStore (all rows)

BUSINESS:
    "Who does what" in content/agent.md: the model plans and explains, the tools do
    every calculation. A weighted average, a count or a total always comes from
    DuckDB, never from the model's arithmetic, so the numbers on screen are the
    tape's numbers. Five tools:
      list_columns    the tape's columns, types and labels
      query_tape      one checked, read-only SELECT (sql_guard.py)
      summarize_tape  the headline numbers: count, UPB, WAC, WA FICO, WA LTV, DQ
      lookup_term     a definition from content/glossary.json
      get_loan        every field of one loan by loan_id

TECH:
    - Each tool is defined ONCE, as JSON Schema (TOOL_SPECS); each provider adapter
      translates the list. Every property is required and additionalProperties is
      false, the shape all three vendors' "strict" modes accept.
    - run() never raises for a bad call. A refused or failed call becomes a
      ToolResult with is_error=True and a reason the model can act on, and
      ToolOutcome.rejected tells the orchestrator to count a guardrail failure.
    - The model gets totals plus the first rows_to_model rows as compact CSV (far
      fewer tokens than JSON). The full result goes to the QueryStore.
    - A loan-level result (one row per loan_id) is widened for the screen with the
      default tape columns (api.toml [columns], Step 4c): add_base_columns. The
      model still reads only the columns its SQL selected (agent_view).
"""

from __future__ import annotations

import csv
import io
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import duckdb

from app.agent.config import Limits
from app.agent.providers.base import ToolCall, ToolResult, ToolSpec
from app.agent.query_store import QueryStore, StoredQuery
from app.agent.loan_tape_link import loan_tape_link
from app.agent.sql_guard import GuardrailError, check_query
from app.loan_query import ColumnTypes, column_kind, select_list

# BUSINESS: loan ids look like LN00012345 (docs/domain/loan-tape-schema.md).
LOAN_ID_PATTERN = re.compile(r"^LN\d{8}$")


def schema(properties: dict[str, Any]) -> dict[str, Any]:
    """A strict JSON Schema object: every property required, nothing extra."""
    return {"type": "object", "properties": properties, "required": list(properties),
            "additionalProperties": False}


TOOL_SPECS: list[ToolSpec] = [
    ToolSpec("list_columns",
             "List the loan tape's columns with their DuckDB type and a readable label with "
             "units. Call this first if unsure of a column name.", schema({})),
    ToolSpec("query_tape",
             "Run ONE read-only DuckDB SELECT over the table `loans` (one row per loan). "
             "Do every count, sum and average in SQL; never compute numbers yourself. "
             "Weighted averages use current_upb: SUM(x * current_upb) / SUM(current_upb). "
             "Rates, LTV and DTI are in percent (6.125 = 6.125%); money in dollars. "
             "No WITH, UNION, comments or other tables. Returns totals and the first rows "
             "as CSV; the visitor sees all rows (up to 500).",
             schema({"title": {"type": "string",
                               "description": "A short title for the result, e.g. 'New York loans by seller'"},
                     "sql": {"type": "string", "description": "One SELECT statement"}})),
    ToolSpec("summarize_tape",
             "The whole tape's headline numbers: loan count, total current UPB, WAC, "
             "WA FICO, WA LTV (all weighted by current UPB), delinquent count, program "
             "mix and MBA delinquency status counts.", schema({})),
    ToolSpec("lookup_term",
             "Look up a mortgage term (e.g. WAC, LTV, Spec story) in LoanIQ's glossary.",
             schema({"term": {"type": "string"}})),
    ToolSpec("get_loan", "Every field of one loan, by loan_id (LN followed by 8 digits).",
             schema({"loan_id": {"type": "string"}})),
]
TOOL_NAMES = {t.name for t in TOOL_SPECS}


@dataclass
class ToolOutcome:
    """What one tool call produced.

    TECH: result goes back to the model; event is the JSON the screen gets (status,
      SQL, query id, row counts); rejected counts as a guardrail failure.
    """
    result: ToolResult
    event: dict[str, Any] = field(default_factory=dict)
    rejected: bool = False


class ToolFailure(Exception):
    """A call that could not run. TECH: rejected=False for honest misses (unknown loan id)."""

    def __init__(self, message: str, rejected: bool = True) -> None:
        super().__init__(message)
        self.rejected = rejected


def plain(value: Any) -> Any:
    """A DuckDB value -> a JSON- and CSV-friendly one.

    TECH: Decimal money -> float (exact to the cent below $1 trillion, see
      loan_query.select_list); dates -> ISO text "2024-05-01".
    """
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def to_csv(columns: list[str], rows: list[list[Any]]) -> str:
    """Rows -> CSV text with a header line. TECH: empty cell for NULL."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows([["" if v is None else v for v in row] for row in rows])
    return buf.getvalue()


def column_totals(columns: list[str], rows: list[list[Any]]) -> dict[str, dict[str, Any]]:
    """Sum, min and max of each numeric column over the returned rows.

    BUSINESS: "the model gets totals": when a result is longer than the rows the
      model sees, it still knows the total balance of all 500 rows.
    TECH: sums in Decimal (from str, so 0.1 stays 0.1), then rounded to cents
      precision for display. Booleans are not numbers here.
    """
    totals: dict[str, dict[str, Any]] = {}
    for i, name in enumerate(columns):
        values = [r[i] for r in rows if isinstance(r[i], (int, float)) and not isinstance(r[i], bool)]
        if values and len(values) == len([r for r in rows if r[i] is not None]):
            total = sum((Decimal(str(v)) for v in values), Decimal(0))
            totals[name] = {"sum": float(round(total, 2)), "min": min(values), "max": max(values)}
    return totals


def run_sql(con: duckdb.DuckDBPyConnection, sql: str, params: list[Any] | dict[str, Any],
            timeout_ms: int) -> tuple[list[str], list[list[Any]]]:
    """Run one query on its own cursor, interrupted after timeout_ms.

    TECH: params is a list for `?` placeholders or a dict for named ones ($p1).
      threading.Timer calls cursor.interrupt() on another thread if the query
      is still running; DuckDB then raises InterruptException. The timer is
      cancelled as soon as the query finishes.
    """
    cur = con.cursor()
    timer = threading.Timer(timeout_ms / 1000, cur.interrupt)
    timer.start()
    try:
        result = cur.execute(sql, params)
        names = [d[0] for d in result.description]
        rows = [[plain(v) for v in row] for row in result.fetchall()]
    except duckdb.InterruptException as exc:
        raise ToolFailure(f"The query took longer than {timeout_ms} ms. Make it simpler.") from exc
    except duckdb.Error as exc:
        raise ToolFailure(f"DuckDB refused the query: {str(exc).splitlines()[0]}") from exc
    finally:
        timer.cancel()
        cur.close()
    return names, rows


class TapeTools:
    """Runs the five tools for one tape.

    TECH:
      con        the read-only DuckDB connection (tape_db.py)
      columns    tape column -> DuckDB type (the allowlist for query_tape)
      labels     tape column -> readable label (content/loan-columns.json)
      glossary   content/glossary.json entries: {term, definition, why}
      summarize  returns (summary dict, the SQL behind it); main.py supplies it so
                 the tool's numbers match the Loan Tape screen exactly
      base_columns  the default columns every loan-level result shows on screen
                 (api.toml [columns]); [] shows only what the SQL selected
    """

    def __init__(self, con: duckdb.DuckDBPyConnection, columns: ColumnTypes,
                 labels: dict[str, str], glossary: list[dict[str, str]],
                 summarize: Callable[[], tuple[dict[str, Any], str]],
                 store: QueryStore, limits: Limits, base_columns: list[str] | None = None) -> None:
        self.con, self.columns, self.labels = con, columns, labels
        self.glossary, self.summarize, self.store, self.limits = glossary, summarize, store, limits
        # TECH: only real tape columns; they are later quoted into SQL, so a name the
        #   tape does not have must never get that far.
        self.base_columns = [c for c in (base_columns or []) if c in columns]

    def run(self, call: ToolCall) -> ToolOutcome:
        """Run one call. Never raises: failures become error results.

        TECH: the input is checked against the tool's schema keys first, because a
          provider without strict mode could send anything.
        """
        handlers = {"list_columns": self.list_columns, "query_tape": self.query_tape,
                    "summarize_tape": self.summarize_tape, "lookup_term": self.lookup_term,
                    "get_loan": self.get_loan}
        event: dict[str, Any] = {"id": call.id, "name": call.name}
        try:
            if call.name not in handlers:
                raise ToolFailure(f"Unknown tool {call.name!r}. Tools: {', '.join(sorted(TOOL_NAMES))}.")
            check_input(call)
            content, data, extra = handlers[call.name](call.input)
        except ToolFailure as exc:
            if call.name == "query_tape" and isinstance(call.input.get("sql"), str):
                event["sql"] = call.input["sql"]
            event.update(status="rejected" if exc.rejected else "failed", reason=str(exc))
            return ToolOutcome(ToolResult(call.id, call.name, f"Error: {exc}", is_error=True),
                               event, rejected=exc.rejected)
        event.update(status="ok", **extra)
        return ToolOutcome(ToolResult(call.id, call.name, content, data=data), event)

    # -- the five tools. Each returns (text for the model, data, extra event fields).

    def list_columns(self, _: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
        """BUSINESS: the model's map of the tape. TECH: one line per column."""
        lines = [f"{n} {t} {column_kind(t)} | {self.labels.get(n, n)}" for n, t in self.columns.items()]
        return "name type kind | label\n" + "\n".join(lines), {"columns": list(self.columns)}, {}

    def query_tape(self, args: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
        """BUSINESS: any question about the tape the desk can write as one SELECT.

        TECH: guard -> run capped query -> count the full match only if capped ->
          store every row -> totals + first rows as CSV for the model.
        """
        stored = self.run_query(args["sql"], args["title"])
        # TECH: the model reads only the columns its own SQL selected, so the added
        #   display columns cost no tokens and cannot change its answer.
        own = agent_view(stored)
        content = query_text(own, self.limits.rows_to_model)
        preview = [dict(zip(own.columns, r)) for r in own.rows[:self.limits.rows_to_model]]
        data = {"query_id": stored.query_id, "row_count": stored.row_count,
                "total_rows": stored.total_rows, "rows": preview}
        # TECH: loan_tape rides on the event so the screen's "Open in Loan Tape"
        #   button is ready as soon as the tool chip appears (Step 4b).
        extra = {"sql": stored.sql, "title": stored.title, "query_id": stored.query_id,
                 "row_count": stored.row_count, "total_rows": stored.total_rows,
                 "truncated": stored.truncated,
                 "loan_tape": stored.loan_tape.model_dump() if stored.loan_tape else None}
        return content, data, extra

    def run_query(self, sql: str, title: str) -> StoredQuery:
        """Check, run and store one SELECT. Shared by query_tape and saved-query reruns.

        BUSINESS: a saved query reruns through exactly the gate the model's SQL
          passes, so a rerun can do nothing the agent could not (Step 4b). A
          loan-level result also shows the default tape columns (Step 4c).
        TECH: guard -> run capped query -> count the full match only if capped ->
          add the default columns -> store every row with its Loan Tape link.
          Raises ToolFailure. The stored SQL and the Loan Tape link are the agent's
          own query; the added columns are for display only.
        """
        lim = self.limits
        try:
            q = check_query(sql, self.columns, lim.max_rows, lim.max_sql_chars)
        except GuardrailError as exc:
            raise ToolFailure(str(exc)) from exc
        names, rows = run_sql(self.con, q.sql, q.params, lim.query_timeout_ms)
        truncated = len(rows) > lim.max_rows
        rows = rows[:lim.max_rows]
        total = run_sql(self.con, q.count_sql, q.params, lim.query_timeout_ms)[1][0][0] if truncated else len(rows)
        names, rows, added = self.add_base_columns(names, rows)
        stored = StoredQuery(query_id=QueryStore.new_id(), title=str(title)[:120],
                             sql=q.display_sql, columns=names, rows=rows, row_count=len(rows),
                             total_rows=total, truncated=truncated,
                             loan_tape=loan_tape_link(q.display_sql, self.columns),
                             added_columns=added)
        self.store.put(stored)
        return stored

    def add_base_columns(self, names: list[str], rows: list[list[Any]]
                         ) -> tuple[list[str], list[list[Any]], list[str]]:
        """Widen a loan-level result with the default tape columns, for the screen.

        BUSINESS: "the 5 largest New York loans" may come back from the agent as just
          loan ID and balance. A trader still wants seller, program, coupon, FICO, LTV
          and the rest beside it, as on the Loan Tape, so every loan-level answer
          shows the same default columns (api.toml [columns]).
        TECH:
          - Applies only when the result has a loan_id column, its column names are
            unique, and no loan_id repeats (one row per loan). Grouped results
            ("UPB by state") and empty results come back unchanged.
          - One extra parameterised query fetches the base columns for the returned
            loan IDs: loan_id IN (SELECT UNNEST(?)), with the IDs as ONE list
            parameter (DuckDB's UNNEST turns a list into rows). Column names come from
            the tape's own column list, never from the model. select_list casts
            money to DOUBLE, as for the grid.
          - Column order: loan_id, then the base columns in tape order (as the Loan
            Tape grid shows them), then the agent's other columns in its order. A base column the agent selected
            keeps the agent's value (it may be computed, e.g. ROUND(ltv) AS ltv).
          - Row order stays the agent's (its ORDER BY): rows are rebuilt in Python
            by loan ID, not re-sorted by DuckDB.
          Returns (columns, rows, names of the columns added).
        """
        if (not rows or not self.base_columns or "loan_id" not in names
                or len(set(names)) != len(names)):
            return names, rows, []
        id_at = names.index("loan_id")
        ids = [r[id_at] for r in rows]
        if len(set(ids)) != len(ids):
            return names, rows, []
        added = [c for c in self.base_columns if c not in names and c != "loan_id"]
        if not added:
            return names, rows, []
        # TECH: fetch the missing base columns for exactly these loans.
        fetch = ["loan_id", *added]
        sql = (f"SELECT {select_list({c: self.columns[c] for c in fetch})} FROM loans "
               "WHERE loan_id IN (SELECT UNNEST(?))")
        _, extra_rows = run_sql(self.con, sql, [ids], self.limits.query_timeout_ms)
        by_id = {r[0]: r[1:] for r in extra_rows}
        # BUSINESS: loan ID first, the trader's default fields next, then whatever
        #   the agent computed for this question (rate spread, loan age, ...).
        order = ["loan_id", *[c for c in self.base_columns if c != "loan_id"],
                 *[n for n in names if n not in self.base_columns and n != "loan_id"]]
        added_at = {c: i for i, c in enumerate(added)}
        own_at = {n: i for i, n in enumerate(names)}
        missing = [None] * len(added)
        out = []
        for r in rows:
            fetched = by_id.get(r[id_at], missing)
            out.append([r[own_at[c]] if c in own_at else fetched[added_at[c]] for c in order])
        return order, out, added

    def summarize_tape(self, _: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
        """BUSINESS: what a trader quotes first about a tape. TECH: the screen's own SQL."""
        summary, sql = self.summarize()
        text = "\n".join(f"{k}: {v}" for k, v in summary.items())
        return text, summary, {"sql": sql}

    def lookup_term(self, args: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
        """BUSINESS: the same definitions the screens' tooltips show.

        TECH: exact match (any case) first, then entries whose term contains the
          asked word or the reverse; at most 3. No match -> a not-found error that
          is not a guardrail failure.
        """
        word = str(args["term"]).strip().lower()
        exact = [g for g in self.glossary if g["term"].lower() == word]
        near = [g for g in self.glossary if word and (word in g["term"].lower() or g["term"].lower() in word)]
        found = (exact or near)[:3]
        if not found:
            raise ToolFailure(f"No glossary entry for {args['term']!r}. Known terms: "
                              + ", ".join(g["term"] for g in self.glossary), rejected=False)
        text = "\n".join(f"{g['term']}: {g['definition']} Why it matters: {g['why']}" for g in found)
        return text, {"terms": [g["term"] for g in found]}, {}

    def get_loan(self, args: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
        """BUSINESS: drill into one loan. TECH: the loan id is a bound parameter."""
        loan_id = str(args["loan_id"]).strip().upper()
        if not LOAN_ID_PATTERN.match(loan_id):
            raise ToolFailure("A loan_id is LN followed by 8 digits, e.g. LN00012345.")
        sql = f"SELECT {select_list(self.columns)} FROM loans WHERE loan_id = ?"
        names, rows = run_sql(self.con, sql, [loan_id], self.limits.query_timeout_ms)
        if not rows:
            raise ToolFailure(f"No loan {loan_id} on this tape.", rejected=False)
        loan = dict(zip(names, rows[0]))
        return "\n".join(f"{k}: {v}" for k, v in loan.items()), {"loan": loan}, {"loan_id": loan_id}


def check_input(call: ToolCall) -> None:
    """The call's input has exactly the schema's keys, as text where text is expected."""
    spec = next(t for t in TOOL_SPECS if t.name == call.name)
    expected = set(spec.input_schema["properties"])
    if not isinstance(call.input, dict) or set(call.input) != expected:
        raise ToolFailure(f"{call.name} takes exactly {sorted(expected) or 'no'} arguments.")
    if any(not isinstance(call.input[k], str) for k in expected):
        raise ToolFailure(f"{call.name}: every argument must be text.")


def agent_view(q: StoredQuery) -> StoredQuery:
    """The result as the agent's SQL produced it: the added display columns removed.

    BUSINESS: the model answers from the columns it asked for; the default columns
      added for the trader's screen (add_base_columns) are not part of its evidence.
    TECH: a copy (Pydantic model_copy) with the added columns dropped from columns
      and from every row; the stored result itself is not changed.
    """
    if not q.added_columns:
        return q
    keep = [i for i, c in enumerate(q.columns) if c not in q.added_columns]
    return q.model_copy(update={"columns": [q.columns[i] for i in keep],
                                "rows": [[r[i] for i in keep] for r in q.rows],
                                "added_columns": []})


def query_text(q: StoredQuery, rows_to_model: int) -> str:
    """The model's view of a result: counts, totals when rows are hidden, CSV.

    TECH: totals cover the returned rows (at most max_rows); total_rows counts
      every match.
    """
    shown = q.rows[:rows_to_model]
    head = f"query_id: {q.query_id}\nrows returned: {q.row_count}"
    if q.truncated:
        head += f" (capped; {q.total_rows} rows match in total)"
    if len(shown) < q.row_count:
        head += f"\nfirst {len(shown)} rows shown below; the visitor sees all {q.row_count}"
        totals = column_totals(q.columns, q.rows)
        if totals:
            head += "\ntotals over the returned rows: " + "; ".join(
                f"{k} sum={v['sum']} min={v['min']} max={v['max']}" for k, v in totals.items())
    return head + "\ncsv:\n" + to_csv(q.columns, shown)
