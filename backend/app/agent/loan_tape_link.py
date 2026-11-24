"""Open an Ask the Tape answer in the Loan Tape: the agent's SQL -> the grid's filter.

Where it sits:
    tools.query_tape / POST /api/ask/rerun -> [loan_tape_link] -> LoanTapeLink
    -> screen's "Open in Loan Tape" -> /?filter=<grid filter JSON>&sort=<col:dir>
    -> Loan Tape grid -> GET /api/loans?filter=... (loan_query.py, the same rules as
       a trader's own column filters)

BUSINESS:
    The agent answers "which NY 30-year loans are under $150K?" with a table. The
    desk then wants those loans in the full grid, with every column, to sort and
    keep filtering. "Open in Loan Tape" does that with the SAME filter, written as
    ordinary column filters the trader can read and change, not as a hidden list of
    loan IDs. When the agent's filter cannot be written as column filters (an OR
    across two columns, a list of five delinquency statuses, a function), the
    button says why instead of opening the grid on the wrong loans.

TECH:
    - sqlglot parses the stored query (already checked by sql_guard.py) and reads
      only its WHERE and ORDER BY. The WHERE must be an AND of simple conditions,
      each one "column <op> value":
          =  <>  >  >=  <  <=     -> equals, notEqual, greaterThan, ... (numbers)
          =                        -> equals (text; the grid's equals ignores case)
          BETWEEN a AND b          -> inRange (numbers, inclusive like SQL)
          IN (a, b)                -> two equals conditions joined with OR
          LIKE / ILIKE '%text%'    -> contains (text)
      AG Grid allows at most 2 conditions per column (gridConfig/loanColumns), so a
      column with more cannot be shown. Anything else -> filter None with a reason.
    - HAVING filters groups, not loans, and a subquery's WHERE is not the outer
      query's, so both are refused rather than half-translated.
    - The result is DATA (a JSON filter model), never SQL. The Loan Tape sends it to
      /api/loans, where loan_query.py checks every column and binds every value.
    - ORDER BY on tape columns becomes the grid's sort ("current_upb:desc"); an
      ORDER BY on an alias or expression is left out (the filter still applies).
      LIMIT is ignored on purpose: the grid shows every matching loan.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import sqlglot
from pydantic import BaseModel, Field
from sqlglot import exp

from app.loan_query import ColumnTypes, column_kind

# TECH: AG Grid's limit on conditions in one column filter (maxNumConditions).
MAX_CONDITIONS_PER_COLUMN = 2
# TECH: SQL comparison node -> AG Grid number filter type; FLIPPED for "125 < ltv".
NUMBER_TYPES = {exp.EQ: "equals", exp.NEQ: "notEqual", exp.GT: "greaterThan",
                exp.GTE: "greaterThanOrEqual", exp.LT: "lessThan", exp.LTE: "lessThanOrEqual"}
FLIPPED = {exp.GT: exp.LT, exp.GTE: exp.LTE, exp.LT: exp.GT, exp.LTE: exp.GTE,
           exp.EQ: exp.EQ, exp.NEQ: exp.NEQ}


class LoanTapeLink(BaseModel):
    """How to open one answer in the Loan Tape.

    BUSINESS: filter is None when the answer's filter cannot be shown as column
      filters; reason then says why, for the button's tooltip.
    TECH: filter is AG Grid's filter model ({} = the whole tape); sort is the
      /api/loans sort string ("col:dir,col:dir") or None.
    """
    filter: dict[str, Any] | None = Field(None, description="AG Grid filter model, or None")
    sort: str | None = Field(None, description="Grid sort, e.g. current_upb:desc")
    reason: str | None = Field(None, description="Why the filter cannot be shown")


class Untranslatable(ValueError):
    """This part of the WHERE has no column-filter form. The message is visitor-facing."""


def loan_tape_link(sql: str, columns: ColumnTypes) -> LoanTapeLink:
    """The agent's checked SQL -> the Loan Tape filter and sort, or a reason.

    BUSINESS: "Open in Loan Tape with the same filter".
    TECH: never raises; any parse problem becomes a reason. sql is the stored
      display SQL (values in place), which sql_guard has already accepted.
    """
    try:
        tree = sqlglot.parse_one(sql, read="duckdb")
        if not isinstance(tree, exp.Select):
            raise Untranslatable("Only a plain SELECT can open in the Loan Tape.")
        if tree.args.get("having") is not None:
            raise Untranslatable("HAVING filters groups, not loans.")
        if any(isinstance(t.this, exp.Subquery) or t.find(exp.Subquery) for t in tree.find_all(exp.From)):
            raise Untranslatable("The query reads from a subquery.")
        where = tree.args.get("where")
        model = grid_filter(where.this, columns) if where is not None else {}
    except Untranslatable as exc:
        return LoanTapeLink(reason=str(exc))
    except sqlglot.errors.SqlglotError:
        return LoanTapeLink(reason="The query could not be read.")
    return LoanTapeLink(filter=model, sort=grid_sort(tree, columns))


def grid_filter(where: exp.Expression, columns: ColumnTypes) -> dict[str, Any]:
    """WHERE condition -> AG Grid filter model {column: filter}.

    BUSINESS: every condition must hold at once, as the grid's columns are ANDed.
    TECH: collects conditions per column, then wraps 2 conditions in AG Grid's
      combined form. An IN of two values is already an OR pair, so it cannot
      share its column with another condition.
    """
    per_column: dict[str, list[tuple[str, list[dict[str, Any]]]]] = {}
    for part in and_parts(where):
        name, operator, conds = condition(part, columns)
        per_column.setdefault(name, []).append((operator, conds))
    model: dict[str, Any] = {}
    for name, groups in per_column.items():
        conds = [c for _, cs in groups for c in cs]
        if len(groups) > 1 and any(op == "OR" for op, _ in groups):
            raise Untranslatable(f"{name} mixes a list of values with another condition.")
        if len(conds) > MAX_CONDITIONS_PER_COLUMN:
            raise Untranslatable(f"{name} has more than {MAX_CONDITIONS_PER_COLUMN} conditions; "
                                 "a grid column holds at most two.")
        operator = groups[0][0] if len(groups) == 1 else "AND"
        kind = conds[0]["filterType"]
        model[name] = conds[0] if len(conds) == 1 else {
            "filterType": kind, "operator": operator, "conditions": conds}
    return model


def and_parts(node: exp.Expression) -> list[exp.Expression]:
    """Split a AND b AND c into [a, b, c]; brackets around a part are removed.

    TECH: an OR anywhere at this level is refused: the grid ANDs its columns.
    """
    while isinstance(node, exp.Paren):
        node = node.this
    if isinstance(node, exp.And):
        return and_parts(node.left) + and_parts(node.right)
    if isinstance(node, exp.Or):
        raise Untranslatable("The filter uses OR across conditions; the grid ANDs its columns.")
    return [node]


def condition(node: exp.Expression, columns: ColumnTypes) -> tuple[str, str, list[dict[str, Any]]]:
    """One simple condition -> (column, "AND"|"OR", AG Grid conditions).

    TECH: raises Untranslatable for any other shape (NOT, IS NULL, a function, a
      date or yes/no column, a comparison between two columns).
    """
    if isinstance(node, exp.Between):
        name, kind = column_of(node.this, columns)
        low, high = value_of(node.args["low"]), value_of(node.args["high"])
        return name, "AND", [number(kind, name, "inRange", low, high)]
    if isinstance(node, exp.In) and not node.args.get("query"):
        name, kind = column_of(node.this, columns)
        values = [value_of(v) for v in node.expressions]
        if len(values) > MAX_CONDITIONS_PER_COLUMN:
            raise Untranslatable(f"{name} is matched against {len(values)} values; a grid "
                                 f"column holds at most {MAX_CONDITIONS_PER_COLUMN}.")
        conds = [equals(kind, name, v) for v in values]
        return name, ("OR" if len(conds) > 1 else "AND"), conds
    if isinstance(node, (exp.Like, exp.ILike)):
        return like(node, columns)
    if type(node) in NUMBER_TYPES:
        return comparison(node, columns)
    raise Untranslatable(f"The condition {node.sql(dialect='duckdb')!r} has no grid filter.")


def comparison(node: exp.Expression, columns: ColumnTypes) -> tuple[str, str, list[dict[str, Any]]]:
    """column <op> value (either way round) -> one number or text condition."""
    op, left, right = type(node), node.left, node.right
    if not isinstance(left, exp.Column):
        op, left, right = FLIPPED[op], right, left
    name, kind = column_of(left, columns)
    value = value_of(right)
    if kind == "text":
        if op is not exp.EQ:
            raise Untranslatable(f"{name}: the grid's text filter can only match equal or contains.")
        return name, "AND", [equals(kind, name, value)]
    return name, "AND", [number(kind, name, NUMBER_TYPES[op], value)]


def like(node: exp.Expression, columns: ColumnTypes) -> tuple[str, str, list[dict[str, Any]]]:
    """col LIKE '%text%' -> contains. TECH: only the two-sided % form, without _ or %."""
    name, kind = column_of(node.this, columns)
    pattern = value_of(node.expression)
    two_sided = isinstance(pattern, str) and len(pattern) > 2 and pattern[0] == pattern[-1] == "%"
    inner = pattern[1:-1] if two_sided else ""
    # TECH: % or _ left inside would be wildcards in SQL but plain text in the grid.
    if kind != "text" or not inner or "%" in inner or "_" in inner:
        raise Untranslatable(f"{name}: only LIKE '%text%' (contains) has a grid filter.")
    return name, "AND", [{"filterType": "text", "type": "contains", "filter": inner}]


def column_of(node: exp.Expression, columns: ColumnTypes) -> tuple[str, str]:
    """A tape column node -> (name, kind). TECH: only text and number kinds filter."""
    if not isinstance(node, exp.Column):
        raise Untranslatable(f"{node.sql(dialect='duckdb')!r} is not a plain column.")
    name = node.name.lower()
    match = next((c for c in columns if c.lower() == name), None)
    if match is None:
        raise Untranslatable(f"{node.name!r} is not a tape column.")
    kind = column_kind(columns[match])
    if kind not in ("text", "number"):
        raise Untranslatable(f"{match} is a {kind} column; the grid has no {kind} filter yet.")
    return match, kind


def value_of(node: exp.Expression) -> Any:
    """A literal (or a negative number) -> its value. TECH: Decimal -> float for JSON."""
    if isinstance(node, exp.Neg):
        inner = value_of(node.this)
        if isinstance(inner, (int, float)):
            return -inner
    if isinstance(node, exp.Literal):
        if node.is_string:
            return node.this
        text = node.this
        return int(text) if text.lstrip("-").isdigit() else float(Decimal(text))
    raise Untranslatable(f"{node.sql(dialect='duckdb')!r} is not a plain value.")


def equals(kind: str, name: str, value: Any) -> dict[str, Any]:
    """An equals condition of the column's own kind."""
    if kind == "text":
        if not isinstance(value, str):
            raise Untranslatable(f"{name} is text but is compared with {value!r}.")
        return {"filterType": "text", "type": "equals", "filter": value}
    return number(kind, name, "equals", value)


def number(kind: str, name: str, filter_type: str, value: Any, value_to: Any = None) -> dict[str, Any]:
    """A number condition. TECH: both values must be numbers, as loan_query requires."""
    values = [value] if value_to is None else [value, value_to]
    if kind != "number" or not all(isinstance(v, (int, float)) for v in values):
        raise Untranslatable(f"{name}: {filter_type} needs a number column and number values.")
    cond = {"filterType": "number", "type": filter_type, "filter": value}
    if value_to is not None:
        cond["filterTo"] = value_to
    return cond


def grid_sort(tree: exp.Select, columns: ColumnTypes) -> str | None:
    """ORDER BY tape columns -> "col:dir,...". TECH: stops at the first non-column key."""
    order = tree.args.get("order")
    if order is None:
        return None
    known = {c.lower(): c for c in columns}
    keys: list[str] = []
    for item in order.expressions:
        col = item.this
        if not isinstance(col, exp.Column) or col.name.lower() not in known:
            break
        keys.append(f"{known[col.name.lower()]}:{'desc' if item.args.get('desc') else 'asc'}")
    return ",".join(keys) or None
