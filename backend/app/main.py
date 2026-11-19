"""The LoanIQ loan API: the synthetic loan tape served from in-memory DuckDB.

Where it sits:
    loan_tape_gen -> data/loan_tape.parquet -> [main: DuckDB table `loans` + API]
    -> grid -> slotting -> best execution -> positions and optimizer -> pool candidates

BUSINESS:
    The desk's first look at a seller's tape is a grid: thousands of loans, sorted by
    balance, filtered to the stories that matter (high LTV, low balance, delinquent).
    This API feeds that grid one page at a time, plus a headline summary: loan count,
    total balance, WAC, WA FICO, WA LTV and the delinquent count, the numbers a
    trader quotes first when describing a pool.

TECH:
    Run from backend/:  .venv\\Scripts\\python.exe -m uvicorn app.main:app --port 8000
    Then open http://localhost:8000/docs for the interactive API page.
    - FastAPI: each function decorated with @app.get(...) is a "route" that answers
      one URL. FastAPI reads the type hints to validate query parameters and to
      build the /docs page; Pydantic models describe every response.
    - Start-up uses a FastAPI "lifespan": code that runs once before the first
      request (load the tape) and once at shutdown (close DuckDB).
    - DuckDB runs in memory: the Parquet file is copied into a table `loans` once,
      so every page, sort and filter is plain SQL over RAM. Each request takes its
      own cursor, so concurrent requests do not share query state.
    - Sorting and filtering SQL is built by app/loan_query.py: column names are
      checked against the real list, values always go in as parameters.
    - create_app(data_dir) lets tests point the API at their own tape folder;
      `app` at the bottom is the real one uvicorn serves.
    Limits (page sizes) live in app/config/api.toml; column labels in
    content/loan-columns.json.
"""

from __future__ import annotations

import json
import tomllib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import duckdb
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app import loan_tape_gen as gen
from app.loan_query import ColumnTypes, QueryError, column_kind, parse_filter, parse_sort, select_list

API_CONFIG_PATH = gen.BACKEND_DIR / "app" / "config" / "api.toml"
LABELS_PATH = gen.REPO_ROOT / "content" / "loan-columns.json"
TAPE_FILE = "loan_tape.parquet"  # TECH: the name loan_tape_gen.write_tape uses

# BUSINESS: the MBA status of a loan that has made every payment. Every other status
#   (30, 60, 90, 120+, FC, BK, REO) counts as delinquent in the summary; see
#   docs/decisions.md.
CURRENT_STATUS = "Current"


def load_api_config(path: Path = API_CONFIG_PATH) -> dict[str, Any]:
    """Read api.toml. TECH: tomllib needs the file opened in binary mode."""
    with path.open("rb") as f:
        return tomllib.load(f)


def load_labels(path: Path = LABELS_PATH) -> dict[str, str]:
    """Read the column -> readable label map from content/loan-columns.json.

    BUSINESS: grid headers say "Current UPB ($)", not current_upb.
    """
    return json.loads(path.read_text(encoding="utf-8"))["labels"]


API_CONFIG = load_api_config()
DEFAULT_LIMIT: int = API_CONFIG["paging"]["default_limit"]
MAX_LIMIT: int = API_CONFIG["paging"]["max_limit"]


# =============================================================================
# Pydantic models: the shape of every request and response
# =============================================================================
# TECH: Pydantic models are classes with typed fields. FastAPI validates input
#   against them and uses them to write the JSON and the /docs page.

class LoansQuery(BaseModel):
    """Query parameters for GET /api/loans.

    BUSINESS: which page of the tape, in what order, with which filters.
    TECH: offset and limit in loans (rows). limit above max_limit (api.toml) is
      capped, not refused. sort is "col:asc|desc[,col:dir...]"; filter is AG Grid's
      filter model as a JSON string.
    """
    offset: int = Field(0, ge=0, description="Rows to skip")
    limit: int = Field(DEFAULT_LIMIT, ge=1, description=f"Rows to return (capped at {MAX_LIMIT})")
    sort: str | None = Field(None, description="For example current_upb:desc,fico:asc")
    filter: str | None = Field(None, description="AG Grid filter model as JSON")


class Health(BaseModel):
    """GET /api/health. BUSINESS: is the tape loaded, and how many loans are in it."""
    status: str
    loans: int


class ColumnInfo(BaseModel):
    """One tape column. TECH: type is the DuckDB type; kind is what the grid filters on."""
    name: str
    type: str
    kind: str
    label: str


class LoansPage(BaseModel):
    """GET /api/loans. TECH: total counts every loan matching the filter, not just this page."""
    rows: list[dict[str, Any]]
    total: int


class Summary(BaseModel):
    """GET /api/loans/summary: the pool's headline numbers.

    BUSINESS: weighted by current UPB, because a $900,000 loan matters more to the
      pool's value than a $90,000 one. Null when the tape is empty.
    TECH: total_current_upb in dollars; wac and wa_ltv in percent; wa_fico in points.
    """
    loan_count: int
    total_current_upb: float
    wac: float | None
    wa_fico: float | None
    wa_ltv: float | None
    delinquent_loans: int


# =============================================================================
# The loan store: one in-memory DuckDB database holding the tape
# =============================================================================

@dataclass
class LoanStore:
    """The loaded tape and its column list.

    BUSINESS: the single copy of the tape every request reads.
    TECH: con is the in-memory DuckDB connection; columns maps name -> DuckDB type,
      in tape order, and is the allow-list for sort and filter column names.
    """
    con: duckdb.DuckDBPyConnection
    columns: ColumnTypes


def ensure_tape(data_dir: Path) -> Path:
    """Return the tape path, generating the default tape first if it is missing.

    BUSINESS: a fresh checkout still starts with a tape, the same one every time
      (generator defaults: seed and size from loan_tape_gen.toml).
    TECH: runs the same code as `python -m app.loan_tape_gen --out-dir <data_dir>`.
    """
    path = data_dir / TAPE_FILE
    if not path.exists():
        gen.main(["--out-dir", str(data_dir)])
    return path


def open_store(data_dir: Path) -> LoanStore:
    """Load the Parquet tape into an in-memory DuckDB table `loans`.

    TECH: ":memory:" means nothing is written to disk. read_parquet(?) takes the
      path as a parameter. DESCRIBE gives the real column names and types.
    """
    path = ensure_tape(data_dir)
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE loans AS SELECT * FROM read_parquet(?)", [str(path)])
    columns = {row[0]: row[1] for row in con.execute("DESCRIBE loans").fetchall()}
    return LoanStore(con=con, columns=columns)


def get_store(request: Request) -> LoanStore:
    """FastAPI dependency: the store loaded at start-up.

    TECH: Depends(get_store) in a route's arguments makes FastAPI call this first
      and pass the result in. The store lives on app.state.
    """
    return request.app.state.store


Store = Annotated[LoanStore, Depends(get_store)]


# =============================================================================
# Queries
# =============================================================================

def fetch_page(store: LoanStore, q: LoansQuery) -> LoansPage:
    """Run one grid page: filtered count plus the sorted, sliced rows.

    BUSINESS: the grid shows "rows 101-200 of 1,234 matching loans".
    TECH: two queries with the same WHERE and parameters: COUNT(*) for the total,
      then SELECT ... ORDER BY ... LIMIT ? OFFSET ?. Money is cast to DOUBLE in
      the SELECT (loan_query.select_list) so it reaches JSON as numbers.
      Raises QueryError for a bad sort or filter.
    """
    where, params = parse_filter(q.filter, store.columns)
    order = parse_sort(q.sort, store.columns)
    where_sql = f"WHERE {where}" if where else ""
    limit = min(q.limit, MAX_LIMIT)
    cur = store.con.cursor()  # TECH: a per-request cursor over the same database
    try:
        total = cur.execute(f"SELECT COUNT(*) FROM loans {where_sql}", params).fetchone()[0]
        sql = (f"SELECT {select_list(store.columns)} FROM loans {where_sql} "
               f"ORDER BY {order} LIMIT ? OFFSET ?")
        result = cur.execute(sql, [*params, limit, q.offset])
        names = [d[0] for d in result.description]
        rows = [dict(zip(names, values)) for values in result.fetchall()]
    finally:
        cur.close()
    return LoansPage(rows=rows, total=total)


# BUSINESS: weighted averages, weighted by current UPB in dollars:
#   WAC     = sum(note_rate x current_upb) / sum(current_upb)   percent
#   WA FICO = sum(fico x current_upb) / sum(current_upb)        points
#   WA LTV  = sum(ltv x current_upb) / sum(current_upb)         percent (original LTV)
# TECH: sums of DECIMAL money stay exact in DuckDB; NULLIF avoids dividing by zero
#   on an empty tape (the average is then NULL). Rounded to 3 decimals for rates
#   (the tape's rate precision) and 2 for FICO and LTV.
SUMMARY_SQL = """
SELECT
    COUNT(*)                                                             AS loan_count,
    COALESCE(SUM(current_upb), 0)                                        AS total_current_upb,
    ROUND(SUM(note_rate * current_upb) / NULLIF(SUM(current_upb), 0), 3) AS wac,
    ROUND(SUM(fico * current_upb)      / NULLIF(SUM(current_upb), 0), 2) AS wa_fico,
    ROUND(SUM(ltv * current_upb)       / NULLIF(SUM(current_upb), 0), 2) AS wa_ltv,
    COUNT(*) FILTER (WHERE dq_status <> ?)                               AS delinquent_loans
FROM loans
"""


def fetch_summary(store: LoanStore) -> Summary:
    """Headline numbers for the whole tape.

    BUSINESS: what a trader quotes first: "2,000 loans, $640mm, 6.4 WAC, 742 FICO,
      78 LTV, 3% delinquent". (Illustrative numbers.)
    TECH: one aggregate query (SUMMARY_SQL). DECIMAL results become float for JSON.
    """
    cur = store.con.cursor()
    try:
        row = cur.execute(SUMMARY_SQL, [CURRENT_STATUS]).fetchone()
    finally:
        cur.close()
    count, total, wac, fico, ltv, dq = row
    return Summary(loan_count=count, total_current_upb=float(total), wac=optional_float(wac),
                   wa_fico=optional_float(fico), wa_ltv=optional_float(ltv), delinquent_loans=dq)


def optional_float(value: Any) -> float | None:
    """TECH: Decimal or float -> float, keeping NULL (empty tape) as None."""
    return None if value is None else float(value)


# =============================================================================
# The app and its routes
# =============================================================================

def create_app(data_dir: Path = gen.DEFAULT_OUT_DIR) -> FastAPI:
    """Build the FastAPI app that serves the tape in data_dir.

    TECH: the lifespan loads the store before the first request and closes DuckDB
      at shutdown. Tests call create_app(tmp_folder) inside `with TestClient(app)`,
      which runs the lifespan.
    """
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.store = open_store(data_dir)
        app.state.labels = load_labels()
        yield
        app.state.store.con.close()

    app = FastAPI(title="LoanIQ loan API", lifespan=lifespan,
                  description="Synthetic loan tape: paged, sorted and filtered in DuckDB. "
                              "All data is synthetic; all numbers illustrative.")

    @app.get("/api/health", response_model=Health)
    def health(store: Store) -> Health:
        """BUSINESS: is the tape loaded. TECH: loan count from COUNT(*)."""
        cur = store.con.cursor()
        try:
            count = cur.execute("SELECT COUNT(*) FROM loans").fetchone()[0]
        finally:
            cur.close()
        return Health(status="ok", loans=count)

    @app.get("/api/loans/columns", response_model=list[ColumnInfo])
    def columns(store: Store, request: Request) -> list[ColumnInfo]:
        """BUSINESS: the grid's column headers. TECH: tape order; label falls back to name."""
        labels: dict[str, str] = request.app.state.labels
        return [ColumnInfo(name=n, type=t, kind=column_kind(t), label=labels.get(n, n))
                for n, t in store.columns.items()]

    @app.get("/api/loans", response_model=LoansPage)
    def loans(store: Store, q: Annotated[LoansQuery, Query()]) -> LoansPage:
        """BUSINESS: one page of the tape. TECH: bad sort or filter -> HTTP 400.

        Annotated[LoansQuery, Query()] tells FastAPI to read the model's fields
        from the URL's query string.
        """
        try:
            return fetch_page(store, q)
        except QueryError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/loans/summary", response_model=Summary)
    def summary(store: Store) -> Summary:
        """BUSINESS: the tape's headline numbers, weighted by current UPB."""
        return fetch_summary(store)

    return app


# TECH: the app uvicorn serves: `uvicorn app.main:app`. Importing this module does
#   not load the tape; that happens in the lifespan when the server starts.
app = create_app()
