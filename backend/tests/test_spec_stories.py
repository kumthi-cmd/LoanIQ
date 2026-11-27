"""Tests for spec-pool stories (backend/app/spec_stories.py, config/spec_stories.toml).

BUSINESS: spec stories decide which loans earn a pay-up over TBA, so their rules
  must be safe, must expand tiers correctly, and the tape must really contain the
  minimum number of loans for each story the desk relies on.
TECH: coverage is checked the way Step 5 will use the rules: by running each
  story's validated `where` in DuckDB against the Parquet file the generator
  writes. Values (file path, product list) go in as query parameters; only the
  validated, re-rendered `where` is placed into the SQL text.
"""

from __future__ import annotations

import copy
from decimal import Decimal
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from app import loan_tape_gen as gen
from app.spec_stories import (SPEC_STORIES_PATH, Story, UnsafeWhereError, equality_target,
                              family, load_spec_stories, validate_where)

CFG = gen.load_config()
STORIES = load_spec_stories(gen.COLUMNS, products=list(CFG["products"]))


def count_story(parquet: Path, story: Story, extra: str = "TRUE") -> int:
    """Number of loans on the tape that have `story`, counted in DuckDB.

    TECH: $path and $products are DuckDB named parameters; list_contains checks
      the loan's product against the story's product list. `extra` is another
      validated rule (used to cut a cumulative LLB tier down to its band).
    """
    sql = (f"SELECT count(*) FROM read_parquet($path) "
           f"WHERE list_contains($products, product) AND ({story.where}) AND ({extra})")
    with duckdb.connect() as con:
        row = con.execute(sql, {"path": str(parquet), "products": list(story.products)}).fetchone()
    return int(row[0])


@pytest.fixture(scope="module")
def parquet(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The default tape written to Parquet once for this module.

    TECH: tmp_path_factory gives a temporary folder shared by the module's tests.
    """
    out = tmp_path_factory.mktemp("tape")
    path, _ = gen.write_tape(gen.generate_tape(), out)
    return path


# -----------------------------------------------------------------------------
# Loading and tier expansion
# -----------------------------------------------------------------------------

def test_tiers_expand_to_one_story_per_cap() -> None:
    """BUSINESS: each LLB cap is its own story, named by its cap (LLB_85K ...)."""
    tiers = family(STORIES, "LLB")
    assert [s.name for s in tiers][:2] == ["LLB_85K", "LLB_110K"]
    assert tiers[0].where == "orig_upb <= 85000"
    assert all(s.family == "LLB" and s.cap is not None for s in tiers)


def test_starting_stories_are_present() -> None:
    """BUSINESS: the four illustrative stories Step 1a starts with."""
    assert {s.family for s in STORIES} == {"LLB", "NY", "PR", "LOW_FICO"}
    assert equality_target(family(STORIES, "NY")[0]) == ("state", "NY")


@pytest.mark.parametrize("text", [
    "state IN ('NY', 'PR') AND fico BETWEEN 600 AND 700",
    "NOT (ltv > 80) OR mod_flag = TRUE",
    "dti <> -1 AND (cltv >= 90.5 OR hcltv < 100)",
])
def test_safe_rules_are_accepted(text: str) -> None:
    """BUSINESS: ordinary desk rules (lists, ranges, negation) are allowed."""
    assert validate_where(text, gen.COLUMNS, "T")


@pytest.mark.parametrize("text, reason", [
    ("fico IN (SELECT fico FROM loans)", "Subquery"),      # subquery
    ("fico < 700; DROP TABLE loans", "semicolon"),          # second statement
    ("favorite_color = 'red'", "unknown column"),           # not a tape column
    ("lower(state) = 'ny'", "Lower"),                       # function call
    ("t.fico < 700", "bare column"),                        # table-qualified column
    ("fico < 700 -- hide", "comment"),                      # SQL comment
    ("fico", "true/false"),                                 # a value, not a test
    ("fico <", "not valid SQL"),                            # does not parse
])
def test_unsafe_rules_are_rejected(text: str, reason: str) -> None:
    """BUSINESS: a story rule can only test loan fields; anything that could read
    other data, run a second statement or hide text is refused with a clear error."""
    with pytest.raises(UnsafeWhereError, match=reason):
        validate_where(text, gen.COLUMNS, "T")


def write_stories(tmp_path: Path, text: str) -> Path:
    """Write a spec_stories.toml variant into a temp folder and return its path."""
    path = tmp_path / "spec_stories.toml"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize("body, reason", [
    ('name = "A"\nproducts = ["30Y Fixed"]\nwhere = "orig_upb <= {cap}"', "if and only if"),
    ('name = "A"\nproducts = ["30Y Fixed"]\nwhere = "fico < 700"\ntiers = [1]', "if and only if"),
    ('name = "A"\nproducts = ["30Y Fixed"]\nwhere = "orig_upb <= {cap}"\ntiers = [200, 100]',
     "strictly increasing"),
    ('name = "A"\nproducts = ["40Y Fixed"]\nwhere = "fico < 700"', "unknown products"),
    ('name = "A"\nproducts = ["30Y Fixed"]\nwhere = "fico < 700"\ncolor = "red"', "unknown keys"),
])
def test_bad_story_tables_are_rejected(tmp_path: Path, body: str, reason: str) -> None:
    """BUSINESS: typos in the story config stop the load instead of mis-tagging."""
    path = write_stories(tmp_path, f"[[story]]\n{body}\n")
    with pytest.raises(ValueError, match=reason):
        load_spec_stories(gen.COLUMNS, products=list(CFG["products"]), path=path)


def test_duplicate_story_names_are_rejected(tmp_path: Path) -> None:
    """TECH: two stories with one name would make tags ambiguous."""
    one = '[[story]]\nname = "A"\nproducts = ["30Y Fixed"]\nwhere = "fico < 700"\n'
    with pytest.raises(ValueError, match="Duplicate"):
        load_spec_stories(gen.COLUMNS, path=write_stories(tmp_path, one + one))


# -----------------------------------------------------------------------------
# Coverage checked in DuckDB
# -----------------------------------------------------------------------------

def covered_stories() -> list[Story]:
    """Every story whose family has a minimum in [coverage.stories]."""
    return [s for s in STORIES if s.family in CFG["coverage"]["stories"]]


@pytest.mark.parametrize("story", covered_stories(), ids=lambda s: s.name)
def test_story_minimum_met_in_duckdb(parquet: Path, story: Story) -> None:
    """BUSINESS: the written tape holds at least the minimum for each story,
    counted with the story's own SQL rule."""
    assert count_story(parquet, story) >= CFG["coverage"]["stories"][story.family]


def test_each_llb_band_meets_minimum_in_duckdb(parquet: Path) -> None:
    """BUSINESS: LLB rules are cumulative (an $80K loan also fits LLB_110K), so the
    stronger promise is checked too: each band between caps has the minimum.
    TECH: the band is this tier's rule AND NOT the previous tier's rule."""
    tiers = family(STORIES, "LLB")
    minimum = CFG["coverage"]["stories"]["LLB"]
    for prev, story in zip([None] + tiers[:-1], tiers):
        extra = "TRUE" if prev is None else f"NOT ({prev.where})"
        assert count_story(parquet, story, extra) >= minimum, story.name


def test_new_tier_is_one_number(tmp_path: Path) -> None:
    """BUSINESS: adding a $300K tier to the config gives LLB_300K its own loans,
    with no code change. Since Step 6a a tier also carries its pay-up, so the new
    tier is its cap plus one pay-up number (6/32, added after LLB_275K's 8)."""
    text = SPEC_STORIES_PATH.read_text(encoding="utf-8").replace("275000]", "275000, 300000]")
    text = text.replace("10, 8]", "10, 8, 6]")
    stories = load_spec_stories(gen.COLUMNS, path=write_stories(tmp_path, text))
    new = [s for s in stories if s.name == "LLB_300K"]
    assert len(new) == 1 and new[0].where == "orig_upb <= 300000"
    path, _ = gen.write_tape(gen.generate_tape(stories=stories), tmp_path)
    previous = family(stories, "LLB")[-2]
    band = count_story(path, new[0], f"NOT ({previous.where})")
    assert band >= CFG["coverage"]["stories"]["LLB"]


def test_minimum_on_unforceable_story_is_an_error() -> None:
    """BUSINESS: the generator refuses a minimum it cannot honestly meet (it does
    not know which field to change for `fico < 700`), rather than falling short."""
    cfg = copy.deepcopy(CFG)
    cfg["coverage"]["stories"]["LOW_FICO"] = 25
    with pytest.raises(ValueError, match="Cannot force story LOW_FICO"):
        gen.generate_tape(cfg=cfg)


def test_low_fico_story_matches_pandas(parquet: Path) -> None:
    """TECH: the SQL rule and a direct pandas filter agree, so DuckDB is reading the
    rule the way the desk means it."""
    story = family(STORIES, "LOW_FICO")[0]
    df = pd.read_parquet(parquet)
    expected = int((df["product"].isin(story.products) & (df["fico"] < 700)).sum())
    assert count_story(parquet, story) == expected


# -----------------------------------------------------------------------------
# Pay-ups (Step 6a)
# -----------------------------------------------------------------------------

def test_payups_load_as_exact_32nds() -> None:
    """BUSINESS: each story carries its full pay-up in 32nds: LLB 85K 64/32 (2
    points), down to LLB 275K 8/32; NY 12, PR 20, Low FICO 8. Illustrative.
    TECH: Decimal, so 12.5 would stay exactly 12.5."""
    payups = {s.name: s.payup_32nds for s in STORIES}
    assert payups["LLB_85K"] == Decimal(64) and payups["LLB_275K"] == Decimal(8)
    assert (payups["NY"], payups["PR"], payups["LOW_FICO"]) == (12, 20, 8)
    assert all(isinstance(v, Decimal) for v in payups.values())


@pytest.mark.parametrize("payups, reason", [
    ("[64, 48]", "one number per tier"),       # two pay-ups for three tiers
    ("[40, 48, 64]", "must not rise"),        # a looser tier paying more
    ("[64, -1, 0]", "0 or more"),
    ("[64, true, 0]", "0 or more"),           # TOML true is not a number of 32nds
    ("12", "one number per tier"),            # a tiered story needs a list
])
def test_bad_tier_payups_are_rejected(tmp_path: Path, payups: str, reason: str) -> None:
    """BUSINESS: a pay-up typo stops the load instead of mispricing a tier."""
    body = ('name = "A"\nproducts = ["30Y Fixed"]\nwhere = "orig_upb <= {cap}"\n'
            f'tiers = [85000, 110000, 150000]\npayup_32nds = {payups}')
    with pytest.raises(ValueError, match=reason):
        load_spec_stories(gen.COLUMNS, path=write_stories(tmp_path, f"[[story]]\n{body}\n"))


def test_untiered_payup_must_be_one_number(tmp_path: Path) -> None:
    """TECH: an untiered story gets one number, not a list."""
    body = 'name = "A"\nproducts = ["30Y Fixed"]\nwhere = "fico < 700"\npayup_32nds = [8]'
    with pytest.raises(ValueError, match="0 or more"):
        load_spec_stories(gen.COLUMNS, path=write_stories(tmp_path, f"[[story]]\n{body}\n"))


def test_payup_is_optional_for_the_loader(tmp_path: Path) -> None:
    """TECH: the tape generator and slotting do not need pay-ups, so the loader
    accepts a story without one (None); pricing is what refuses it
    (tests/test_pricing_model.py)."""
    body = 'name = "A"\nproducts = ["30Y Fixed"]\nwhere = "fico < 700"'
    story = load_spec_stories(gen.COLUMNS, path=write_stories(tmp_path, f"[[story]]\n{body}\n"))[0]
    assert story.payup_32nds is None
