"""Safe SQL building for the loan grid: sort and filter -> parameterized DuckDB SQL.

Where it sits:
    loan tape -> DuckDB table `loans` -> [loan_query] -> loan API (main.py) -> grid
    -> slotting -> best execution -> positions and optimizer -> pool candidates

BUSINESS:
    A trader slices the tape constantly: "show me everything over 125 LTV",
    "largest balances first", "only New York". The grid sends those requests to the
    server, and this module turns them into SQL so DuckDB does the work over the
    whole tape, not just the rows already in the browser. A wrong filter here would
    show the desk the wrong loans, so the rules are strict: anything we do not
    understand is rejected with a clear error instead of being guessed at.

TECH:
    Two inputs arrive from the browser:
      sort    "current_upb:desc,fico:asc"   -> ORDER BY clause
      filter  AG Grid's filter model JSON  -> WHERE clause + parameter list
    Safety, the two rules that prevent SQL injection:
      1. Column names cannot be SQL parameters, so every name is checked against the
         real column list (from DESCRIBE loans) and then double-quoted.
      2. Every value (numbers, text) goes in as a `?` parameter; DuckDB sends it
         separately from the SQL text, so it can never change the query's meaning.
    Every problem raises QueryError; main.py turns it into HTTP 400.
    Supported AG Grid filters (anything else is a 400):
      text   (string columns):  contains, equals    (case-insensitive, like AG Grid)
      number (numeric columns): equals, greaterThan, lessThan, inRange
      plus AG Grid's combined form: {"operator": "AND"|"OR", "conditions": [...]}.
"""

from __future__ import annotations

import json
from typing import Any

# TECH: column name -> DuckDB type string as DESCRIBE reports it,
#   for example {"current_upb": "DECIMAL(14,2)", "state": "VARCHAR"}.
ColumnTypes = dict[str, str]
# TECH: a piece of SQL and the parameter values for its `?` placeholders, in order.
SqlPart = tuple[str, list[Any]]

# BUSINESS: the loan key. Added as the last sort key so two loans with the same
#   balance always come back in the same order, and paging never shows a loan twice
#   or skips one.
TIEBREAK_COLUMN = "loan_id"

NUMBER_TYPE_PREFIXES = ("DECIMAL", "INTEGER", "BIGINT", "SMALLINT", "TINYINT",
                        "DOUBLE", "FLOAT", "REAL", "HUGEINT", "UBIGINT", "UINTEGER")
# TECH: AG Grid number filter type -> SQL comparison. inRange is handled separately.
NUMBER_OPERATORS = {"equals": "=", "greaterThan": ">", "lessThan": "<"}
TEXT_TYPES = ("contains", "equals")
COMBINE_OPERATORS = ("AND", "OR")


class QueryError(ValueError):
    """A sort or filter the API refuses.

    BUSINESS: better to tell the desk "unknown column" than to quietly show
      the whole tape as if a filter had been applied.
    TECH: main.py maps it to HTTP 400 with the message as the detail.
    """


def column_kind(duck_type: str) -> str:
    """Group a DuckDB type into what the grid needs: text, number, date or boolean.

    BUSINESS: the grid offers "greater than" on balances and "contains" on
      seller names; the kind decides which filters a column gets.
    TECH: DECIMAL(14,2) money, INTEGER and DOUBLE are all "number".
      Unknown types fall back to "text".
    """
    upper = duck_type.upper()
    if upper.startswith(NUMBER_TYPE_PREFIXES):
        return "number"
    if upper == "DATE":
        return "date"
    if upper == "BOOLEAN":
        return "boolean"
    return "text"


def quote_column(name: str, columns: ColumnTypes) -> str:
    """Return the column as a quoted SQL identifier, or raise QueryError.

    TECH: the allow-list check is what makes it safe to put the name in SQL text.
      Quoting with "" also guards against any name that is a SQL keyword.
    """
    if name not in columns:
        raise QueryError(f"Unknown column: {name!r}")
    return f'"{name}"'


def select_list(columns: ColumnTypes) -> str:
    """The SELECT list for grid rows, with money cast to DOUBLE.

    BUSINESS: balances are stored to the exact cent; the grid needs them as numbers
      so it can sort, total and format them as dollars.
    TECH: DuckDB returns DECIMAL as Python Decimal, which JSON would send as a string.
      DOUBLE becomes a JSON number. A 2-decimal value under $1 trillion fits
      exactly enough in a double that it round-trips to the same cents.
    """
    parts = []
    for name, duck_type in columns.items():
        quoted = f'"{name}"'
        if duck_type.upper().startswith("DECIMAL"):
            parts.append(f"CAST({quoted} AS DOUBLE) AS {quoted}")
        else:
            parts.append(quoted)
    return ", ".join(parts)


def parse_sort(sort: str | None, columns: ColumnTypes) -> str:
    """Turn "col:dir,col:dir" into an ORDER BY clause (without the keyword).

    BUSINESS: "largest balance first" is current_upb:desc. Ties are broken by
      loan ID so every page is stable.
    TECH: direction defaults to asc; only asc and desc are allowed (case-insensitive).
      NULLS LAST keeps fixed-rate loans (null ARM fields) at the bottom both ways.
      Raises QueryError on an unknown column or direction.
    """
    keys: list[str] = []
    seen: set[str] = set()
    for item in (sort or "").split(","):
        item = item.strip()
        if not item:
            continue
        name, _, direction = item.partition(":")
        direction = (direction or "asc").strip().lower()
        if direction not in ("asc", "desc"):
            raise QueryError(f"Sort direction must be asc or desc, got {direction!r}")
        keys.append(f"{quote_column(name.strip(), columns)} {direction.upper()} NULLS LAST")
        seen.add(name.strip())
    # TECH: the tie-break goes last so it never overrides what the user asked for.
    if TIEBREAK_COLUMN in columns and TIEBREAK_COLUMN not in seen:
        keys.append(f'"{TIEBREAK_COLUMN}" ASC')
    return ", ".join(keys)


def require_number(value: Any, field: str) -> float | int:
    """Check a number filter value. TECH: bool is an int in Python, so it is refused."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise QueryError(f"Number filter needs a numeric {field!r}, got {value!r}")
    return value


def escape_like(text: str) -> str:
    r"""Escape LIKE wildcards so user text matches literally.

    TECH: in LIKE, % means "anything" and _ means "any one character". A search for
      "50_50" should not match "50X50", so \, % and _ get a backslash in front,
      and the SQL says ESCAPE '\'.
    """
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def text_condition(col: str, cond: dict[str, Any]) -> SqlPart:
    """One AG Grid text condition -> SQL, for string columns.

    BUSINESS: "seller contains 'bay'" finds every seller with bay in the name,
      whatever the capitalization, the same way the grid's own filter behaves.
    TECH: contains -> col ILIKE '%text%' (ILIKE = case-insensitive LIKE);
      equals -> lower(col) = lower(text).
    """
    kind, value = cond.get("type"), cond.get("filter")
    if kind not in TEXT_TYPES:
        raise QueryError(f"Unsupported text filter type: {kind!r}")
    if not isinstance(value, str):
        raise QueryError(f"Text filter needs a string 'filter', got {value!r}")
    if kind == "contains":
        return f"{col} ILIKE ? ESCAPE '\\'", [f"%{escape_like(value)}%"]
    return f"lower({col}) = lower(?)", [value]


def number_condition(col: str, cond: dict[str, Any]) -> SqlPart:
    """One AG Grid number condition -> SQL, for numeric columns.

    BUSINESS: "LTV greater than 125" is the classic high-LTV screen; "current UPB in
      range 100,000 to 200,000" finds the loan-balance tiers.
    TECH: equals/greaterThan/lessThan -> =, >, <. inRange -> BETWEEN filter AND
      filterTo, inclusive at both ends (AG Grid's default). Values are parameters.
    """
    kind = cond.get("type")
    if kind == "inRange":
        low = require_number(cond.get("filter"), "filter")
        high = require_number(cond.get("filterTo"), "filterTo")
        return f"{col} BETWEEN ? AND ?", [low, high]
    if kind not in NUMBER_OPERATORS:
        raise QueryError(f"Unsupported number filter type: {kind!r}")
    return f"{col} {NUMBER_OPERATORS[kind]} ?", [require_number(cond.get("filter"), "filter")]


def single_condition(name: str, cond: dict[str, Any], columns: ColumnTypes) -> SqlPart:
    """Check the condition fits the column's kind, then build its SQL.

    TECH: a text filter on a number column (or the reverse) is a 400, not a guess.
    """
    col = quote_column(name, columns)
    filter_type, kind = cond.get("filterType"), column_kind(columns[name])
    if filter_type == "text" and kind == "text":
        return text_condition(col, cond)
    if filter_type == "number" and kind == "number":
        return number_condition(col, cond)
    raise QueryError(f"Filter type {filter_type!r} is not supported on {kind} column {name!r}")


def column_condition(name: str, model: Any, columns: ColumnTypes) -> SqlPart:
    """One column's filter, simple or combined (AND/OR of conditions).

    BUSINESS: "FICO under 680 OR over 800" is one column, two conditions.
    TECH: AG Grid's combined form is {"filterType", "operator", "conditions": [...]};
      each condition is built alone and joined, wrapped in brackets so OR inside one
      column cannot leak into the AND between columns.
    """
    if not isinstance(model, dict):
        raise QueryError(f"Filter for {name!r} must be an object")
    if "conditions" not in model:
        return single_condition(name, model, columns)
    operator = str(model.get("operator", "AND")).upper()
    conditions = model["conditions"]
    if operator not in COMBINE_OPERATORS:
        raise QueryError(f"Filter operator must be AND or OR, got {operator!r}")
    if not isinstance(conditions, list) or not conditions:
        raise QueryError(f"Filter for {name!r} needs a non-empty 'conditions' list")
    parts: list[SqlPart] = []
    for cond in conditions:
        if not isinstance(cond, dict):
            raise QueryError(f"Each condition for {name!r} must be an object")
        # TECH: conditions usually repeat filterType; fall back to the outer one if not.
        parts.append(single_condition(name, {"filterType": model.get("filterType"), **cond},
                                      columns))
    sql = f" {operator} ".join(p[0] for p in parts)
    return f"({sql})", [v for p in parts for v in p[1]]


def parse_filter(filter_json: str | None, columns: ColumnTypes) -> SqlPart:
    """AG Grid filter model JSON -> (WHERE clause without the keyword, parameters).

    BUSINESS: every column filter the trader sets must hold at once, so the
      columns are joined with AND.
    TECH: returns ("", []) for no filter. The model is {column: filter, ...}.
      Raises QueryError for bad JSON, a non-object, or any rejected condition.
    """
    if not filter_json or not filter_json.strip():
        return "", []
    try:
        model = json.loads(filter_json)
    except json.JSONDecodeError as exc:
        raise QueryError(f"Filter is not valid JSON: {exc.msg}") from exc
    if not isinstance(model, dict):
        raise QueryError("Filter must be a JSON object of column -> filter")
    parts = [column_condition(name, spec, columns) for name, spec in model.items()]
    return " AND ".join(p[0] for p in parts), [v for p in parts for v in p[1]]
