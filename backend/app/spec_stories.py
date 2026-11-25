"""Spec-pool stories: load, expand and validate the rules in spec_stories.toml.

Where it sits:
    config/spec_stories.toml -> [spec_stories] -> loan_tape_gen (coverage now)
                                               -> slotting (app/slotting.py, Step 5a)

BUSINESS:
    A spec story is a loan feature, such as a low balance, New York or a low FICO,
    that makes a pool prepay slowly and so earns a pay-up over TBA. The desk
    defines each story as a rule ("which loans qualify"). Keeping the rules in one
    config file means a new tier or story is a config change, not a code change.
    All stories and tiers are illustrative; sources are in docs/public-sources.md.

TECH:
    Each rule's `where` is a SQL boolean expression over loan tape columns, so it
    is treated as code, not trusted text. When the config loads, sqlglot (a SQL
    parser) turns each expression into a syntax tree, and every node of that tree
    must be on a short allowlist: tape columns, comparisons, AND/OR/NOT, IN,
    BETWEEN, parentheses and literals. Semicolons and comments are refused before
    parsing. The SQL kept for later use is sqlglot's re-rendering of the checked
    tree, never the raw text. Tiered stories ({cap} placeholder plus a tiers list)
    expand into one story per cap, named like LLB_85K.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import sqlglot
from sqlglot import exp  # TECH: exp holds sqlglot's syntax-tree node classes

SPEC_STORIES_PATH = Path(__file__).resolve().parent / "config" / "spec_stories.toml"

# TECH: the only syntax-tree nodes a `where` may contain.
#   Comparisons: EQ (=), NEQ (<>), GT, GTE, LT, LTE. Neg is a minus sign on a
#   number (-1). Identifier is the name part inside a Column node.
ALLOWED_NODES: tuple[type[exp.Expression], ...] = (
    exp.And, exp.Or, exp.Not, exp.Paren,
    exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE, exp.In, exp.Between,
    exp.Column, exp.Identifier, exp.Literal, exp.Boolean, exp.Neg,
)
# TECH: the whole expression must be a yes/no test, not a bare value like `fico`.
PREDICATE_ROOTS: tuple[type[exp.Expression], ...] = (
    exp.And, exp.Or, exp.Not, exp.Paren,
    exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE, exp.In, exp.Between,
)
STORY_KEYS = {"name", "products", "where", "tiers"}
CAP = "{cap}"


class UnsafeWhereError(ValueError):
    """A story's rule is not a safe, simple test over tape columns.

    BUSINESS: a bad rule must stop the app loudly rather than mis-tag loans.
    TECH: subclass of ValueError, so callers can catch either.
    """


@dataclass(frozen=True)
class Story:
    """One spec story, after tier expansion and validation.

    BUSINESS: "loans with product in `products` and `where` true have this story".
    TECH: `where` is sqlglot's rendering of the validated tree (DuckDB dialect),
      safe to place inside a WHERE clause. `family` is the config name (LLB);
      `name` adds the cap for tiered stories (LLB_85K). `cap` is None if untiered.
    """

    name: str
    family: str
    products: tuple[str, ...]
    where: str
    cap: float | None = None


def validate_where(text: str, columns: Sequence[str], story: str, kind: str = "Story") -> str:
    """Check one `where` expression and return its normalized SQL.

    BUSINESS: only plain tests on loan fields are allowed, e.g. "state = 'NY'",
      "fico < 700", "orig_upb <= 85000".
    TECH: refuses `;` and comments before parsing (sqlglot would otherwise keep
      only the first statement, or carry comments into its output). Then requires
      exactly one parsed statement, a yes/no root, allowlisted nodes only, and
      unqualified columns that exist on the tape. Raises UnsafeWhereError.
      `kind` names the rule type in error messages ("Story", or "Desk question" when
      app/desk_questions.py reuses this check), so the message points at the right file.
    """
    if ";" in text or "--" in text or "/*" in text:
        raise UnsafeWhereError(f"{kind} {story}: semicolons and comments are not allowed: {text!r}")
    try:
        parsed = sqlglot.parse(text, read="duckdb")
    except sqlglot.errors.ParseError as err:
        raise UnsafeWhereError(f"{kind} {story}: not valid SQL: {text!r} ({err})") from err
    if len(parsed) != 1 or parsed[0] is None:
        raise UnsafeWhereError(f"{kind} {story}: must be exactly one expression: {text!r}")
    tree = parsed[0]
    if not isinstance(tree, PREDICATE_ROOTS):
        raise UnsafeWhereError(f"{kind} {story}: must be a true/false test: {text!r}")
    for node in tree.walk():
        check_node(node, columns, story, text, kind)
    return tree.sql(dialect="duckdb")


def check_node(node: exp.Expression, columns: Sequence[str], story: str, text: str,
               kind: str = "Story") -> None:
    """Reject one syntax-tree node unless it is allowlisted.

    TECH: columns must be bare names (no `table.` prefix) from the tape schema.
      The error names the offending construct, e.g. "Subquery" or "Lower" (a
      function call).
    """
    if not isinstance(node, ALLOWED_NODES):
        raise UnsafeWhereError(
            f"{kind} {story}: {type(node).__name__} is not allowed in a rule: {text!r}")
    if isinstance(node, exp.Column):
        if node.table:
            raise UnsafeWhereError(f"{kind} {story}: use bare column names, not {node.sql()!r}")
        if node.name not in columns:
            raise UnsafeWhereError(f"{kind} {story}: unknown column {node.name!r}: {text!r}")


def cap_label(cap: float) -> str:
    """Tier suffix from the cap in dollars: 85000 -> "85K", 82500 -> "82.5K"."""
    return f"{cap / 1000:g}K"


def check_entry(entry: dict[str, Any], products: Sequence[str] | None) -> None:
    """Structural checks on one [[story]] table before its rule is parsed.

    BUSINESS: catches typos (an unknown product, tiers that go down) at load time.
    TECH: raises ValueError with the story's name in the message.
    """
    name = entry.get("name", "<unnamed>")
    unknown = set(entry) - STORY_KEYS
    missing = {"name", "products", "where"} - set(entry)
    if unknown or missing:
        raise ValueError(f"Story {name}: unknown keys {sorted(unknown)}, missing {sorted(missing)}")
    if products is not None and set(entry["products"]) - set(products):
        raise ValueError(f"Story {name}: unknown products {sorted(set(entry['products']) - set(products))}")
    tiers = entry.get("tiers")
    if (tiers is not None) != (CAP in entry["where"]):
        raise ValueError(f"Story {name}: use {CAP} in `where` if and only if `tiers` is given")
    if tiers is not None and (not tiers or any(b <= a for a, b in zip(tiers, tiers[1:]))
                              or tiers[0] <= 0):
        raise ValueError(f"Story {name}: tiers must be positive and strictly increasing")


def expand_story(entry: dict[str, Any], columns: Sequence[str],
                 products: Sequence[str] | None = None) -> list[Story]:
    """Turn one [[story]] table into validated Story objects (one per tier).

    BUSINESS: `LLB` with tiers [85000, 110000] becomes LLB_85K and LLB_110K.
    TECH: {cap} is replaced with the cap as a plain number (no format() call, so
      other braces are never interpreted), then the result is validated.
    """
    check_entry(entry, products)
    family, prods = entry["name"], tuple(entry["products"])
    if "tiers" not in entry:
        return [Story(family, family, prods, validate_where(entry["where"], columns, family))]
    out = []
    for cap in entry["tiers"]:
        name = f"{family}_{cap_label(cap)}"
        text = entry["where"].replace(CAP, f"{cap:g}")
        out.append(Story(name, family, prods, validate_where(text, columns, name), float(cap)))
    return out


def load_spec_stories(columns: Sequence[str], products: Sequence[str] | None = None,
                      path: Path = SPEC_STORIES_PATH) -> list[Story]:
    """Load, expand and validate every story in the config file.

    BUSINESS: the single entry point; if any rule is unsafe, nothing loads.
    TECH: `columns` is the tape schema (passed in, so this module does not import
      the generator); `products`, if given, is the list of known product names.
      Raises ValueError (or UnsafeWhereError) on any problem, including duplicates.
    """
    with path.open("rb") as f:
        entries = tomllib.load(f).get("story", [])
    stories = [s for entry in entries for s in expand_story(entry, columns, products)]
    names = [s.name for s in stories]
    if len(names) != len(set(names)):
        raise ValueError(f"Duplicate story names: {sorted({n for n in names if names.count(n) > 1})}")
    return stories


def family(stories: Sequence[Story], name: str) -> list[Story]:
    """All stories of one config family, tiers in increasing cap order."""
    found = sorted((s for s in stories if s.family == name), key=lambda s: s.cap or 0)
    if not found:
        raise ValueError(f"No story named {name} in spec_stories.toml")
    return found


def equality_target(story: Story) -> tuple[str, str] | None:
    """(column, value) if the rule is exactly `column = 'text'`, else None.

    BUSINESS: lets the generator move a loan into a story like NY by setting
      state = 'NY'.
    TECH: parses the already-validated SQL again; only an EQ between a column and
      a string literal counts.
    """
    tree = sqlglot.parse_one(story.where, read="duckdb")
    if isinstance(tree, exp.EQ) and isinstance(tree.this, exp.Column) \
            and isinstance(tree.expression, exp.Literal) and tree.expression.is_string:
        return tree.this.name, tree.expression.this
    return None


def tier_column(story: Story) -> str | None:
    """Column name if the rule is exactly `column <= number`, else None.

    BUSINESS: lets the generator fill a balance tier by setting orig_upb.
    """
    tree = sqlglot.parse_one(story.where, read="duckdb")
    if isinstance(tree, exp.LTE) and isinstance(tree.this, exp.Column) \
            and isinstance(tree.expression, exp.Literal) and not tree.expression.is_string:
        return tree.this.name
    return None
