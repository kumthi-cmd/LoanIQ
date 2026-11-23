"""Tests for the build facts: content/build-facts.json and how test.ps1 writes it.

Where it sits: test.ps1 (Write-BuildFacts, after every layer passes) ->
  content/build-facts.json (committed) -> the Docker image's SPA build -> the
  "By the numbers" tiles on How it was built.

BUSINESS: protects the evidence on the How it was built page: the numbers are only
  written after a fully green run, the committed file holds real counts a visitor can
  trust, and adding the step did not break the rule that CI runs exactly what
  test.ps1 runs.
TECH: reads test.ps1 and the JSON file as text; no PowerShell needed, so this runs in
  CI on Linux too. The five-layer check itself lives in test_deploy_config.py.
"""

from __future__ import annotations

import json
import re

from app import loan_tape_gen as gen

REPO_ROOT = gen.REPO_ROOT
FACTS = REPO_ROOT / "content" / "build-facts.json"
TEST_PS1 = REPO_ROOT / "test.ps1"

# TECH: the keys test.ps1 writes and BuildFacts.tsx reads (content.ts BuildFacts).
COUNT_KEYS = ("backendTests", "frontendTests", "e2eTests", "commits")


def test_committed_facts_have_every_key_with_sane_values() -> None:
    """BUSINESS: the live site shows a full set of believable numbers, not dashes.

    TECH: counts are positive whole numbers; coverage is a percent at or above the
      80% floor (a run under it fails before the file is written); date is ISO.
    """
    facts = json.loads(FACTS.read_text(encoding="utf-8"))
    assert set(facts) == {*COUNT_KEYS, "backendCoverage", "date"}
    for key in COUNT_KEYS:
        assert isinstance(facts[key], int) and facts[key] > 0, key
    assert 80 <= facts["backendCoverage"] <= 100
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", facts["date"])


def test_committed_facts_file_has_no_byte_order_mark() -> None:
    """TECH: Windows PowerShell 5.1 writes a BOM by default; Vite's JSON import and
    git diffs are cleaner without one, so test.ps1 writes plain UTF-8."""
    assert not FACTS.read_bytes().startswith(b"\xef\xbb\xbf")


def test_facts_are_written_only_after_every_layer_passed() -> None:
    """BUSINESS: a failing run never updates the numbers on the page.

    TECH: the call to Write-BuildFacts comes after the try/catch that exits 1 on any
      failure, and after the last Invoke-Step (Playwright).
    """
    text = TEST_PS1.read_text(encoding="utf-8")
    call = text.rindex("Write-BuildFacts $runStarted")
    assert text.rindex("exit 1") < call
    assert text.rindex('Invoke-Step "End to end: Playwright"') < call


def test_write_build_facts_is_a_plain_function_not_a_layer() -> None:
    """BUSINESS: green on GitHub keeps meaning the same as green on your PC.

    TECH: test_deploy_config.py counts the Invoke-Step layers and checks ci.yml runs
      the same ones; the facts step must not add a sixth. CI does not write the file.
    """
    text = TEST_PS1.read_text(encoding="utf-8")
    assert re.search(r"^function Write-BuildFacts\(", text, flags=re.MULTILINE)
    assert not re.search(r'Invoke-Step\s+"[^"]*[Bb]uild facts', text)
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "build-facts" not in ci


def test_front_end_count_comes_from_the_vitest_json_report() -> None:
    """BUSINESS: the front-end number counts every test that ran.

    TECH: test.ps1 reads the report path that vite.config.ts configures, so the two
      must name the same file.
    """
    vite = (REPO_ROOT / "frontend" / "vite.config.ts").read_text(encoding="utf-8")
    assert '["json", { outputFile: "test-results/vitest.json" }]' in vite
    assert r"frontend\test-results\vitest.json" in TEST_PS1.read_text(encoding="utf-8")
