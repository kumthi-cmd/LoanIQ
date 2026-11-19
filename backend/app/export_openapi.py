"""Write the loan API's OpenAPI spec to frontend/src/api/openapi.json.

Where it sits:
    loan API (main.py) -> [export_openapi] -> openapi.json -> `npm run gen:api`
    -> frontend/src/api/schema.d.ts -> the SPA's typed API calls

BUSINESS:
    The grid and the KPI tiles must read the same fields the API sends: if the API
    renames wa_ltv, the screen should fail to build, not quietly show a blank tile.

TECH:
    Run from backend/:  .venv\\Scripts\\python.exe -m app.export_openapi
    - OpenAPI is the standard JSON description of an HTTP API. FastAPI builds it from
      the routes and Pydantic models (app.openapi()), without starting a server or
      loading the tape.
    - openapi-typescript (front end) turns the JSON into TypeScript types, so no
      type for API data is written by hand (.claude/rules/frontend.md).
    - The JSON is committed. tests/test_spa.py fails if it drifts from the code,
      which is the reminder to rerun this script and `npm run gen:api`.
    - Keys are sorted and indented so a change shows up as a readable git diff.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app import loan_tape_gen as gen
from app.main import app

OPENAPI_PATH = gen.REPO_ROOT / "frontend" / "src" / "api" / "openapi.json"


def openapi_text() -> str:
    """The spec as stable JSON text. TECH: sorted keys, 2-space indent, final newline."""
    spec: dict[str, Any] = app.openapi()
    return json.dumps(spec, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> Path:
    """Write the spec and return its path. TECH: --out overrides the default path."""
    parser = argparse.ArgumentParser(description="Export the LoanIQ OpenAPI spec")
    parser.add_argument("--out", type=Path, default=OPENAPI_PATH, help="output JSON file")
    out: Path = parser.parse_args(argv).out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(openapi_text(), encoding="utf-8")
    print(f"Wrote {out}")
    return out


if __name__ == "__main__":  # pragma: no cover - TECH: the command-line entry point
    main()
