"""The LoanIQ loan API: the synthetic loan tape served from in-memory DuckDB.

Where it sits:
    loan_tape_gen -> data/loan_tape.parquet -> [main: DuckDB table `loans` + API]
    -> grid -> slotting -> best execution -> positions and optimizer -> pool candidates

BUSINESS:
    The desk's first look at a seller's tape is a grid: thousands of loans, sorted by
    balance, filtered to the stories that matter (high LTV, low balance, delinquent).
    This API feeds that grid one page at a time, plus a headline summary: loan count,
    total balance, WAC, WA FICO, WA LTV and the delinquent count, the numbers a
    trader quotes first when describing a pool. It also feeds the screen's three
    panels (program mix, note-rate buckets, MBA delinquency) and the desk-question
    chips ("LTV over 125", "New York", ...), which filter the grid with one click.

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
    - Desk questions (config/desk_questions.toml) are validated SQL rules loaded at
      start-up by app/desk_questions.py. The browser sends only a question id
      (?question=ltv_over_125), never SQL; an unknown id is a 400.
    - The panel queries live in app/tape_panels.py.
    - create_app(data_dir) lets tests point the API at their own tape folder;
      `app` at the bottom is the real one uvicorn serves.
    - The same server also serves the built single-page app (frontend/dist, from
      `npm run build`) at "/", so the whole of LoanIQ runs on one port in production
      and in the Playwright tests. In dev mode Vite serves the SPA instead and
      proxies /api here. See serve_spa() and docs/decisions.md.
    - Product slotting (Step 5a): the rules (config/slotting.toml and
      spec_stories.toml) are checked at start-up, so a bad rule stops the app. A
      run happens only on POST /api/slotting/run (app/slotting_api.py). When it
      publishes, the grid switches from the `loans` table to the view
      `loans_slotted`, which adds two columns, slot and spec_stories; until then
      the Loan Tape is the seller's tape alone.
    - Ask the Tape (Step 4a): the agent in app/agent/ is built in the lifespan
      (app.state.ask) and its routes (POST /api/ask, GET /api/ask/queries/{id}) are
      added from app/agent/api.py with include_router. Its summarize_tape tool uses
      tape_summary() below, so the agent quotes the same numbers as the screen.
    - The price file (Step 6a): config/pricing.toml is checked at start-up against
      the slotting rules, and app/pricing/ builds app.state.prices. Nothing is
      fetched at start-up: the first GET /api/prices/grid of each New York day
      fetches Treasury's curve (app/pricing/treasury.py).
    Limits (page sizes), panel settings (note-rate buckets, status order) and the
    default columns both screens show live in app/config/api.toml; column labels in content/loan-columns.json; chip labels in
    content/desk-questions.json; the agent's models and limits in app/config/llm.toml.
"""

from __future__ import annotations

import json
import tomllib
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import duckdb
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app import loan_tape_gen as gen
from app.agent import api as ask_api
from app.agent.config import AgentConfig
from app.agent.providers.base import LLMProvider
from app.agent.service import build_ask_service, close_ask_service
from app.desk_questions import DESK_QUESTIONS_PATH, DeskQuestion, load_desk_questions
from app.loan_query import ColumnTypes, QueryError, column_kind, parse_filter, parse_sort, select_list
from app import slotting_api
from app.pricing import api as pricing_api
from app.pricing.config import load_pricing_config
from app.pricing.sources import build_price_source
from app.pricing.treasury import Fetch
from app.slotting import (GRID_COLUMNS, GRID_VIEW, SlottingRules, add_agent_columns, agent_column_labels,
                          load_slotting_rules, load_slotting_words, story_labels)
from app.slotting_api import SlottingService
from app.tape_panels import (Breakdowns, QuestionCount, TapeInfo, bucket_spec, fetch_breakdowns,
                             fetch_question_counts, fetch_tape_info)

API_CONFIG_PATH = gen.BACKEND_DIR / "app" / "config" / "api.toml"
LABELS_PATH = gen.REPO_ROOT / "content" / "loan-columns.json"
TAPE_FILE = "loan_tape.parquet"  # TECH: the name loan_tape_gen.write_tape uses
# TECH: where `npm run build` (Vite) writes the single-page app.
SPA_DIR = gen.REPO_ROOT / "frontend" / "dist"

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


def agent_contributions(rules: SlottingRules | None, words: dict[str, Any]) -> dict[str, Any]:
    """What each stage adds to Ask the Tape's copy of the tape (agent/stages.py).

    BUSINESS: today only Product Slotting: its flat columns, from the same rules as
      the Loan Tape. Best execution and the later stages add theirs here.
    TECH: stage id -> a function of the copy's write connection.
    """
    if rules is None:
        return {}
    return {"slotting": lambda con: add_agent_columns(con, rules, words)}


def agent_labels(labels: dict[str, str], rules: SlottingRules | None, words: dict[str, Any]) -> dict[str, str]:
    """Labels for the agent's list_columns: the grid's, plus the agent's slot columns."""
    return {**labels, **(agent_column_labels(rules, words) if rules else {})}


def all_labels() -> dict[str, str]:
    """Headers for every grid column: the tape's own, then the two slotting adds.

    TECH: slot labels live with the other slotting words in content/slotting.json,
      so loan-columns.json stays exactly the tape's fields.
    """
    return {**load_labels(), **load_slotting_words()["labels"]}


API_CONFIG = load_api_config()
DEFAULT_LIMIT: int = API_CONFIG["paging"]["default_limit"]
MAX_LIMIT: int = API_CONFIG["paging"]["max_limit"]
# BUSINESS: the note-rate buckets and the delinquency status order of the panels
#   (illustrative display settings, api.toml [breakdowns]).
# TECH: bucket_spec checks the settings when this module loads, so a bad config
#   fails at start-up, not on the first request.
RATE_BUCKETS = bucket_spec(API_CONFIG["breakdowns"])
DQ_STATUS_ORDER: list[str] = API_CONFIG["breakdowns"]["dq_status_order"]
# BUSINESS: the fields a trader reads first, shown by default on the Loan Tape and in
#   every loan-level Ask the Tape result (illustrative display choice, api.toml
#   [columns]). TECH: filtered to the tape's real columns, in tape order, by
#   default_columns().
DEFAULT_VISIBLE_COLUMNS: list[str] = API_CONFIG["columns"]["default_visible"]


def default_columns(columns: ColumnTypes, wanted: list[str] = DEFAULT_VISIBLE_COLUMNS) -> list[str]:
    """The default columns this tape actually has, in TAPE order.

    BUSINESS: one list for both screens, so the Loan Tape and an Ask the Tape answer
      open on the same fields in the same left-to-right order.
    TECH: walks the tape's columns (DESCRIBE order, loan_id first) and keeps those
      named in the config, so the config's own order does not matter and a repeated
      name cannot appear twice. A configured name the tape does not have is
      dropped, not an error, so a test tape with fewer columns still works.
    """
    return [n for n in columns if n in wanted]


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
      filter model as a JSON string. question is a desk-question id from
      config/desk_questions.toml; it is ANDed with the filter.
    """
    offset: int = Field(0, ge=0, description="Rows to skip")
    limit: int = Field(DEFAULT_LIMIT, ge=1, description=f"Rows to return (capped at {MAX_LIMIT})")
    sort: str | None = Field(None, description="For example current_upb:desc,fico:asc")
    filter: str | None = Field(None, description="AG Grid filter model as JSON")
    question: str | None = Field(None, description="Desk question id, for example ltv_over_125")


class Health(BaseModel):
    """GET /api/health. BUSINESS: is the tape loaded, and how many loans are in it."""
    status: str
    loans: int


class ColumnInfo(BaseModel):
    """One tape column.

    BUSINESS: default_visible marks the fields a trader reads first; the Loan Tape
      opens with only those showing (api.toml [columns]).
    TECH: type is the DuckDB type; kind is what the grid filters on. The API always
      sends default_visible, so the generated TypeScript type makes it required.
    """
    name: str
    type: str
    kind: str
    label: str
    default_visible: bool = False


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

    BUSINESS: the single copy of the tape every request reads, and the desk
      questions that can be asked of it.
    TECH: con is the in-memory DuckDB connection; columns maps name -> DuckDB type,
      in tape order, and is the allow-list for sort and filter column names.
      questions maps id -> validated rule, in config order (empty in tests that
      build a store by hand). columns is always the seller's tape alone.
      slotting is the validated slotting rules (None in hand-built stores).
      grid is what the Loan Tape pages: None means the `loans` table and its
      columns; after a slotting run, (view name, columns plus the slot columns).
      It is one attribute, replaced in one assignment, so a request never sees a
      view name with the old column list or the reverse.
    """
    con: duckdb.DuckDBPyConnection
    columns: ColumnTypes
    questions: dict[str, DeskQuestion] = field(default_factory=dict)
    slotting: SlottingRules | None = None
    grid: tuple[str, ColumnTypes] | None = None

    def grid_source(self) -> tuple[str, ColumnTypes]:
        """(table or view, columns) the Loan Tape grid reads. TECH: one attribute read."""
        return self.grid or ("loans", self.columns)

    def show_slots(self) -> None:
        """BUSINESS: the Loan Tape gains Slot and Spec Stories once slotting publishes.

        TECH: called by the slotting run right after its transaction commits.
        """
        self.grid = (GRID_VIEW, {**self.columns, **GRID_COLUMNS})


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


def open_store(data_dir: Path, questions_path: Path = DESK_QUESTIONS_PATH) -> LoanStore:
    """Load the Parquet tape into an in-memory DuckDB table `loans`, plus the desk questions
    and the slotting rules.

    BUSINESS: the tape loads unslotted; slotting runs when a visitor asks (Step 5a).
    TECH: ":memory:" means nothing is written to disk. read_parquet(?) takes the
      path as a parameter. DESCRIBE gives the real column names and types, which
      the desk-question and slotting rules are then checked against; slotting's
      program and product names are checked against the generator's config. A bad
      rule raises here, so the API does not start (the connection is closed first).
    """
    path = ensure_tape(data_dir)
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE loans AS SELECT * FROM read_parquet(?)", [str(path)])
    columns = {row[0]: row[1] for row in con.execute("DESCRIBE loans").fetchall()}
    try:
        questions = load_desk_questions(list(columns), questions_path)
        cfg = gen.load_config()
        rules = load_slotting_rules(list(columns), list(cfg["programs"]), list(cfg["products"]))
    except ValueError:
        con.close()
        raise
    return LoanStore(con=con, columns=columns, questions=questions, slotting=rules)


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

def question_where(store: LoanStore, question_id: str | None) -> str:
    """The validated SQL rule for a desk question id, or "" for no question.

    BUSINESS: "LTV over 125" clicked on screen arrives as ?question=ltv_over_125.
    TECH: the id is only a dictionary key: the SQL comes from the config file,
      never from the request. An unknown id raises QueryError (HTTP 400).
    """
    if not question_id:
        return ""
    if question_id not in store.questions:
        raise QueryError(f"Unknown desk question: {question_id!r}")
    return store.questions[question_id].where


def grid_where(store: LoanStore, columns: ColumnTypes, grid_filter: str | None,
               question: str | None) -> tuple[str, list[Any]]:
    """The WHERE clause for the grid's filter and desk question, with its parameters.

    BUSINESS: a desk question and the grid's column filters must all hold at once
      ("New York" AND "FICO under 700"); after slotting, a filter on Slot or Spec
      Stories works the same way.
    TECH: columns is the allow-list for filter column names (the grid's columns).
      Each part in brackets, joined with AND, so an OR inside one can never leak
      into the other. The question rule has no `?` placeholders, so the parameter
      list is the filter's alone. "" when there is nothing to filter. Raises
      QueryError for a bad filter or question id.
    """
    where, params = parse_filter(grid_filter, columns)
    parts = [f"({w})" for w in (where, question_where(store, question)) if w]
    return (f"WHERE {' AND '.join(parts)}" if parts else ""), params


def fetch_page(store: LoanStore, q: LoansQuery) -> LoansPage:
    """Run one grid page: filtered count plus the sorted, sliced rows.

    BUSINESS: the grid shows "rows 101-200 of 1,234 matching loans", with Slot and
      Spec Stories once slotting has run.
    TECH: the table (`loans`, or the view `loans_slotted` after a run) and its
      columns come from one read of store.grid_source(). Two queries with the same
      WHERE and parameters: COUNT(*) for the total, then SELECT ... ORDER BY ...
      LIMIT ? OFFSET ?. Money is cast to DOUBLE in the SELECT
      (loan_query.select_list) so it reaches JSON as numbers. Raises QueryError for
      a bad sort, filter or question id.
    """
    table, columns = store.grid_source()
    where_sql, params = grid_where(store, columns, q.filter, q.question)
    order = parse_sort(q.sort, columns)
    limit = min(q.limit, MAX_LIMIT)
    cur = store.con.cursor()  # TECH: a per-request cursor over the same database
    try:
        total = cur.execute(f"SELECT COUNT(*) FROM {table} {where_sql}", params).fetchone()[0]
        sql = (f"SELECT {select_list(columns)} FROM {table} {where_sql} "
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


def tape_summary(store: LoanStore) -> tuple[dict[str, Any], str]:
    """The Ask the Tape summarize_tape tool: headline numbers, program mix, MBA status.

    BUSINESS: the agent quotes exactly the numbers on the Loan Tape screen's tiles
      and panels, because it calls the same functions.
    TECH: returns (summary, SQL shown on screen). Program mix and status counts are
      compact text ("Conventional 1,014 loans $..."), cheaper in tokens than JSON.
    """
    summary = fetch_summary(store).model_dump()
    panels = fetch_breakdowns(store.con, RATE_BUCKETS, DQ_STATUS_ORDER)
    summary["program_mix"] = "; ".join(f"{p.program} {p.loans:,} loans ${p.current_upb:,.2f}"
                                       for p in panels.programs)
    summary["dq_status"] = "; ".join(f"{s.status} {s.loans:,}" for s in panels.dq_status)
    return summary, SUMMARY_SQL.strip().replace("?", f"'{CURRENT_STATUS}'")


# =============================================================================
# The app and its routes
# =============================================================================

def spa_file(spa_dir: Path, path: str) -> Path | None:
    """Pick the file of the built SPA that answers a browser URL.

    BUSINESS: a trader can bookmark or reload any screen (say /slotting later) and
      land on it, instead of getting "not found".
    TECH: a real file inside spa_dir (index.html, assets/app-1a2b.js, favicon) is
      returned as is. Any other path gets index.html, and React Router in the browser
      then picks the screen from the URL. Paths that escape spa_dir ("../") are
      refused by the resolve() + is_relative_to check, so the server can never hand
      out files outside the build folder. None when there is no build yet.
    """
    index = spa_dir / "index.html"
    if not index.is_file():
        return None
    candidate = (spa_dir / path).resolve()
    if path and candidate.is_relative_to(spa_dir.resolve()) and candidate.is_file():
        return candidate
    return index


def build_pricing(rules: SlottingRules | None, slotting_words: dict[str, Any],
                  fetch: Fetch | None,
                  clock: Callable[[], datetime] = lambda: datetime.now(UTC)
                  ) -> pricing_api.PricingService | None:
    """The price file service (Step 6a), or None in a hand-built store with no rules.

    BUSINESS: the price grid uses the same story labels as the Loan Tape.
    TECH: load_pricing_config raises on a bad setting, which stops the app.
      clock (an aware datetime) decides the New York day for the curve and the
      SIFMA Current month (Step 6b); tests pass a fixed one.
    """
    if rules is None:
        return None
    cfg = load_pricing_config(rules)
    return pricing_api.PricingService(build_price_source(cfg, fetch, clock),
                                      pricing_api.load_pricing_words(),
                                      story_labels(rules, slotting_words))


def create_app(data_dir: Path = gen.DEFAULT_OUT_DIR, spa_dir: Path = SPA_DIR,
               questions_path: Path = DESK_QUESTIONS_PATH,
               agent_config: AgentConfig | None = None,
               ask_providers: dict[str, LLMProvider] | None = None,
               price_fetch: Fetch | None = None) -> FastAPI:
    """Build the FastAPI app that serves the tape in data_dir and the SPA in spa_dir.

    TECH: the lifespan loads the store before the first request and closes DuckDB
      at shutdown. Tests call create_app(tmp_folder) inside `with TestClient(app)`,
      which runs the lifespan. spa_dir is the Vite build; tests pass their own, and
      questions_path lets a test load a deliberately broken desk-question config.
      agent_config and ask_providers let tests run Ask the Tape on their own limits
      and on a FakeProvider; by default llm.toml and the real adapters are used.
      price_fetch replaces the Treasury download (url -> XML bytes) in tests, so
      they never touch the network.
    """
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        store = open_store(data_dir, questions_path)
        app.state.store = store
        app.state.labels = all_labels()
        words = load_slotting_words()
        app.state.ask = build_ask_service(
            data_dir / TAPE_FILE, store.columns, agent_labels(app.state.labels, store.slotting, words),
            {qid: q.where for qid, q in store.questions.items()},
            lambda: tape_summary(store), agent_config, ask_providers,
            base_columns=DEFAULT_VISIBLE_COLUMNS,
            contributions=agent_contributions(store.slotting, words),
            grid_columns=lambda: store.grid_source()[1],
            slotting=(store.slotting, words) if store.slotting else None)
        # BUSINESS: Product Slotting (Step 5a): one shared result for every visitor.
        #   When a run publishes, the Loan Tape shows the new columns and Ask the Tape
        #   learns the Slotting stage (Step 5c), its copy rebuilt in the background.
        ask_tape = app.state.ask.tape

        def published() -> None:
            store.show_slots()
            ask_tape.add_stage_async("slotting")

        app.state.slotting = SlottingService(store.con, store.slotting, words, on_publish=published)
        app.state.prices = build_pricing(store.slotting, words, price_fetch)
        yield
        close_ask_service(app.state.ask)
        store.con.close()

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
        """BUSINESS: the grid's column headers, and which ones show at first. After a
        slotting run the list ends with Slot and Spec Stories.

        TECH: tape order; label falls back to name; default_visible from api.toml,
        checked against the grid's columns, so Slot and Spec Stories show by default
        once a run exists (Step 5b).
        """
        labels: dict[str, str] = request.app.state.labels
        _, grid_columns = store.grid_source()
        shown = set(default_columns(grid_columns))
        return [ColumnInfo(name=n, type=t, kind=column_kind(t), label=labels.get(n, n),
                           default_visible=n in shown)
                for n, t in grid_columns.items()]

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

    @app.get("/api/loans/breakdowns", response_model=Breakdowns)
    def breakdowns(store: Store) -> Breakdowns:
        """BUSINESS: the three summary panels (program mix, note-rate buckets, MBA
        delinquency), whole tape. TECH: settings from api.toml [breakdowns]."""
        return fetch_breakdowns(store.con, RATE_BUCKETS, DQ_STATUS_ORDER)

    @app.get("/api/loans/questions", response_model=list[QuestionCount])
    def questions(store: Store) -> list[QuestionCount]:
        """BUSINESS: each desk-question chip's loan count, whole tape.
        TECH: config order; the same rules /api/loans?question= applies."""
        return fetch_question_counts(store.con, list(store.questions.values()))

    @app.get("/api/tape", response_model=TapeInfo)
    def tape(store: Store) -> TapeInfo:
        """BUSINESS: "41 fields · 6 fictional sellers" under the screen title."""
        return fetch_tape_info(store.con, len(store.columns))

    # BUSINESS: Ask the Tape (Step 4a), Product Slotting (Step 5a) and the price
    #   file (Step 6a).
    # TECH: before the catch-all below.
    app.include_router(ask_api.router)
    app.include_router(slotting_api.router)
    app.include_router(pricing_api.router)

    # TECH: registered last, so every /api route above wins first. "{path:path}" is a
    #   FastAPI path parameter that matches the rest of the URL, slashes included.
    #   include_in_schema=False keeps it off the /docs page and the OpenAPI spec.
    @app.get("/{path:path}", include_in_schema=False)
    def serve_spa(path: str) -> FileResponse:
        """BUSINESS: the LoanIQ screens. TECH: unknown /api/... stays a JSON 404;
        no build yet -> 404 with a hint to run `npm run build`."""
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Unknown API route")
        file = spa_file(spa_dir, path)
        if file is None:
            raise HTTPException(status_code=404,
                                detail="The SPA is not built. Run `npm run build` in frontend/.")
        return FileResponse(file)

    return app


# TECH: the app uvicorn serves: `uvicorn app.main:app`. Importing this module does
#   not load the tape; that happens in the lifespan when the server starts.
app = create_app()
