"""Tests for the deployment files at the repo root: Dockerfile, .dockerignore, .nvmrc.

Where it sits: these files are not Python, but they decide what goes live. A wrong
  line there passes every other test and only breaks on the host. These checks run
  on every machine, in seconds, without Docker. The CI "container" job
  (.github/workflows/ci.yml) is the full test: it builds and runs the real image.

BUSINESS: protects what a visitor gets from the live site: the same code, Python and
  Node versions that passed the tests here, the same seeded synthetic tape, a server
  that answers on the host's port, and no secrets or local data inside the image.
TECH: reads the files as plain text (no Docker or YAML library needed). A tiny parser
  turns the Dockerfile into (INSTRUCTION, arguments) pairs, joining lines that end
  in a backslash and dropping comments. Paths the app uses are read from the app's
  own constants (main.SPA_DIR, main.LABELS_PATH, gen.DEFAULT_OUT_DIR), so if code
  moves a folder, these tests fail until the Dockerfile follows.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from app import loan_tape_gen as gen
from app import main

REPO_ROOT = gen.REPO_ROOT
DOCKERFILE = REPO_ROOT / "Dockerfile"
DOCKERIGNORE = REPO_ROOT / ".dockerignore"
NVMRC = REPO_ROOT / ".nvmrc"

# TECH: where the image puts the repo. Every path below is checked relative to this.
CONTAINER_ROOT = "/app"


# =============================================================================
# Helpers
# =============================================================================

def dockerfile_instructions(path: Path = DOCKERFILE) -> list[tuple[str, str]]:
    """The Dockerfile as a list of (INSTRUCTION, arguments), in order.

    BUSINESS: lets each test ask a plain question of the build ("which user runs
      the app?") instead of matching raw text.
    TECH: drops blank lines and comments (# ...), joins continuation lines (ending
      in a backslash) into one instruction. The parser directive on line 1
      (# syntax=...) is a comment here too. Instruction names are upper-cased.
    """
    instructions: list[tuple[str, str]] = []
    pending = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # TECH: a trailing backslash means the instruction carries on to the next line.
        if line.endswith("\\"):
            pending += line[:-1] + " "
            continue
        keyword, _, args = (pending + line).partition(" ")
        instructions.append((keyword.upper(), " ".join(args.split())))
        pending = ""
    return instructions


def stages(instructions: list[tuple[str, str]]) -> list[list[tuple[str, str]]]:
    """Split the instructions into build stages, one list per FROM.

    TECH: in a multi-stage build only the last stage is the image that runs.
    """
    result: list[list[tuple[str, str]]] = []
    for keyword, args in instructions:
        if keyword == "FROM":
            result.append([])
        result[-1].append((keyword, args))
    return result


def base_image_version(stage: list[tuple[str, str]], image: str) -> str:
    """The version tag of a stage's base image, e.g. "3.12" from python:3.12-slim."""
    keyword, args = stage[0]
    match = re.match(rf"{image}:(\d+(?:\.\d+)?)", args)
    assert keyword == "FROM" and match, f"expected FROM {image}:<version>, got {args!r}"
    return match.group(1)


def copy_destinations(stage: list[tuple[str, str]]) -> list[str]:
    """Every COPY destination in a stage, as a path under CONTAINER_ROOT, no trailing /.

    TECH: the destination is the last word of a COPY. Relative destinations are
      relative to the WORKDIR in force at that point, which this follows.
    """
    workdir = "/"
    result: list[str] = []
    for keyword, args in stage:
        if keyword == "WORKDIR":
            workdir = args if args.startswith("/") else f"{workdir.rstrip('/')}/{args}"
        elif keyword == "COPY":
            dest = args.split()[-1]
            full = dest if dest.startswith("/") else f"{workdir.rstrip('/')}/{dest}"
            result.append(full.rstrip("/"))
    return result


def in_container(local: Path) -> str:
    """Where a repo path lives inside the image, e.g. <repo>/frontend/dist -> /app/frontend/dist."""
    return f"{CONTAINER_ROOT}/{local.relative_to(REPO_ROOT).as_posix()}"


RUNTIME = stages(dockerfile_instructions())[-1]
SPA_STAGE = stages(dockerfile_instructions())[0]


# =============================================================================
# Versions: the image runs what the tests ran
# =============================================================================

def test_runtime_python_matches_the_local_venv() -> None:
    """BUSINESS: the live API runs on the Python version every back-end test ran on.

    TECH: pytest runs inside backend/.venv (locally) or the CI venv, so
      sys.version_info is the tested version. Major.minor must match the
      python:<x.y>-slim tag; patch versions may differ.
    """
    tested = f"{sys.version_info.major}.{sys.version_info.minor}"
    assert base_image_version(RUNTIME, "python") == tested


def test_spa_stage_node_matches_nvmrc() -> None:
    """BUSINESS: the screens a visitor sees are built with the Node the tests used.

    TECH: .nvmrc holds the Node major version once; CI's setup-node reads it, and
      the Dockerfile's node:<major>-slim tag must agree.
    """
    assert base_image_version(SPA_STAGE, "node") == NVMRC.read_text(encoding="utf-8").strip()


def test_local_node_matches_nvmrc() -> None:
    """BUSINESS: the build on your PC and the build in the image use the same Node.

    TECH: runs `node --version` (e.g. "v26.13.1") and compares the major version.
      test.ps1 needs Node anyway, so a missing Node is a failure, not a skip.
    """
    node = shutil.which("node")
    assert node, "Node is not on PATH; test.ps1 needs it for the front-end layers"
    version = subprocess.run([node, "--version"], capture_output=True, text=True,
                             check=True).stdout.strip()
    assert version.lstrip("v").split(".")[0] == NVMRC.read_text(encoding="utf-8").strip()


# =============================================================================
# Layout: the paths in main.py and loan_tape_gen.py resolve inside the image
# =============================================================================

def test_runtime_copies_every_folder_the_app_reads() -> None:
    """BUSINESS: the live site has its screens, its column labels and its explanations.

    TECH: main.SPA_DIR (the built SPA) and main.LABELS_PATH (inside content/) are
      found from REPO_ROOT, so each must be copied to the same place under /app.
      The back end itself must sit at /app/backend for REPO_ROOT to be /app.
    """
    copied = copy_destinations(RUNTIME)
    assert in_container(gen.BACKEND_DIR) in copied
    assert in_container(main.SPA_DIR) in copied
    assert in_container(main.LABELS_PATH.parent) in copied


def test_runtime_copies_the_spa_from_the_build_stage() -> None:
    """BUSINESS: the image serves the SPA built from this commit, not a stale local one.

    TECH: frontend/dist is in .dockerignore, so the only way in is from stage 1.
    """
    spa = in_container(main.SPA_DIR)
    assert ("COPY", f"--from=spa {spa} {main.SPA_DIR.relative_to(REPO_ROOT).as_posix()}") in RUNTIME


def test_spa_stage_has_what_vite_reads() -> None:
    """BUSINESS: the built screens include their explanations and the LoanIQ Labs logo.

    TECH: vite.config.ts reads ../content and ../brand, so stage 1 copies both next
      to frontend/ before `npm run build`.
    """
    copied = copy_destinations(SPA_STAGE)
    for folder in ("content", "brand", "frontend"):
        assert f"{CONTAINER_ROOT}/{folder}" in copied
    assert ("RUN", "cd frontend && npm run build") in SPA_STAGE


def test_tape_is_generated_at_build_time_with_generator_defaults() -> None:
    """BUSINESS: every deploy serves the same seeded synthetic tape, and starts fast.

    TECH: `python -m app.loan_tape_gen` with no arguments uses the size and seed in
      loan_tape_gen.toml and writes <repo>/data, which must be /app/data. It runs
      from /app/backend so `app` is importable, and before USER, as root, so the
      tape is read-only to the app.
    """
    assert gen.DEFAULT_OUT_DIR == REPO_ROOT / "data"
    run = ("RUN", "python -m app.loan_tape_gen")
    assert run in RUNTIME
    before = RUNTIME[: RUNTIME.index(run)]
    workdirs = [args for keyword, args in before if keyword == "WORKDIR"]
    assert workdirs[-1] == in_container(gen.BACKEND_DIR)
    assert not any(keyword == "USER" for keyword, _ in before)


# =============================================================================
# Running: non-root, on the host's port
# =============================================================================

def test_app_runs_as_a_non_root_user() -> None:
    """BUSINESS: a break-in to the web server would not have full control of the container.

    TECH: the last USER before CMD names someone other than root (or uid 0).
    """
    users = [args for keyword, args in RUNTIME if keyword == "USER"]
    assert users and users[-1] not in ("root", "0")
    assert [keyword for keyword, _ in RUNTIME][-1] == "CMD"


def test_server_listens_on_all_interfaces_and_the_hosts_port() -> None:
    """BUSINESS: the host can reach the app on the port it chose, 10000 by default.

    TECH: uvicorn must bind 0.0.0.0 (not 127.0.0.1) inside a container, and read
      $PORT when the container starts: "${PORT:-10000}" is shell syntax for "$PORT,
      or 10000 if unset", so CMD must go through sh -c.
    """
    cmd = RUNTIME[-1][1]
    assert cmd.startswith('["sh", "-c", "exec uvicorn app.main:app')
    assert "--host 0.0.0.0" in cmd
    assert "--port ${PORT:-10000}" in cmd
    assert ("ENV", "PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PORT=10000") in RUNTIME


# =============================================================================
# .dockerignore: no secrets, no local data, nothing the build needs left out
# =============================================================================

def dockerignore_patterns() -> set[str]:
    """The patterns in .dockerignore, without comments or blank lines."""
    lines = DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip() and not line.strip().startswith("#")}


@pytest.mark.parametrize("pattern", [
    ".git", "**/.env", "**/.venv", "**/node_modules", "frontend/dist", "data/",
    "**/.coverage", "**/.pytest_cache", "**/htmlcov", "e2e/test-results", "e2e/playwright-report",
])
def test_dockerignore_keeps_out_secrets_local_builds_and_test_output(pattern: str) -> None:
    """BUSINESS: no secrets and no local, unreviewed data go into an image on the internet.

    TECH: each pattern keeps one thing out of the build context. node_modules and
      .venv use "**/" because they exist in more than one folder.
    """
    assert pattern in dockerignore_patterns()


@pytest.mark.parametrize("folder", ["backend", "content", "brand", "frontend"])
def test_dockerignore_does_not_drop_what_the_build_copies(folder: str) -> None:
    """BUSINESS: the image is never built without its code, words or logo.

    TECH: a COPY of a folder that .dockerignore leaves out fails the build.
    """
    patterns = dockerignore_patterns()
    assert not {folder, f"{folder}/", f"/{folder}", f"**/{folder}"} & patterns
