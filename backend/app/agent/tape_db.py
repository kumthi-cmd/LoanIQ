"""The agent's own read-only copy of the tape: a DuckDB file nothing can write to,
rebuilt as the desk finishes each stage.

Where it sits:
    data/loan_tape.parquet + finished stages (agent/stages.py) -> [tape_db.AgentTape]
    -> tools.TapeTools (every tool call) ; a stage publishes -> AgentTape.add_stage

BUSINESS: the model's queries run against a copy of the tape that is read-only at
  the database level. Even if a query got past the SQL checks, it could not change
  the tape the grid shows, write a file, or read anything else on the server. From
  Step 5c the copy also holds what each finished stage produced (Product Slotting's
  flat columns today), so the agent's scope grows as the desk works the tape.
TECH:
  - The grid's tape is an in-memory DuckDB database, and DuckDB cannot open an
    in-memory database read-only. So the Parquet tape is loaded into a scratch
    in-memory database, each finished stage adds its columns there, and the result is
    written once to a DuckDB file in a fresh temporary folder (about 1 MB for 2,000
    loans), which is then opened with read_only=True.
  - enable_external_access=False stops read_csv, read_parquet, COPY ... TO and
    ATTACH from touching the file system or the network. lock_configuration=True
    stops any SET statement from switching it back on.
  - AgentTape holds the current copy (a TapeSnapshot). A tool call borrows it with
    lease() for the length of that one call. A rebuild makes a whole new copy in a
    new folder, then swaps it in under a lock; the old copy is closed and its folder
    deleted only when its last lease ends, so a query in flight always finishes on
    the copy it started on.
  - Rebuilds run one at a time (a second lock) and, after a publish, on a background
    thread (add_stage_async), so the run that published is not slowed down.
  - Every folder is new, so a stale copy can never be read; close() deletes the last.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import threading
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from app.agent.stages import STAGE_IDS, TAPE
from app.loan_query import ColumnTypes

# TECH: a stage's contribution: given the copy's WRITE connection with `loans` in
#   it, add that stage's columns (slotting.add_agent_columns, bound in main.py).
Contribution = Callable[[duckdb.DuckDBPyConnection], None]
log = logging.getLogger(__name__)
READ_ONLY_CONFIG = {"enable_external_access": False, "lock_configuration": True}


@dataclass
class ReadOnlyTape:
    """The read-only connection and the folder holding its file.

    TECH: con is shared by all agent requests; each tool call takes its own cursor.
    """
    con: duckdb.DuckDBPyConnection
    folder: Path


def open_readonly_tape(parquet_path: Path) -> ReadOnlyTape:
    """Copy the Parquet tape into a new DuckDB file and open it read-only.

    TECH: the write connection is closed before the read-only one opens; DuckDB
      allows only one writer, and none is needed after the copy.
    """
    folder = Path(tempfile.mkdtemp(prefix="loaniq-agent-"))
    db_path = folder / "tape.duckdb"
    writer = duckdb.connect(str(db_path))
    try:
        writer.execute("CREATE TABLE loans AS SELECT * FROM read_parquet(?)", [str(parquet_path)])
    finally:
        writer.close()
    con = duckdb.connect(str(db_path), read_only=True, config=READ_ONLY_CONFIG)
    return ReadOnlyTape(con=con, folder=folder)


def close_readonly_tape(tape: ReadOnlyTape) -> None:
    """Close the connection and delete the temporary folder. TECH: safe to call twice."""
    tape.con.close()
    shutil.rmtree(tape.folder, ignore_errors=True)


@dataclass
class TapeSnapshot:
    """One built copy: its connection, columns, the stages in it, and who is using it.

    BUSINESS: built_at is when the copy took in its stages (the slot card's run time).
    TECH: columns comes from DESCRIBE, so the guard's allowlist and list_columns are
      always exactly this copy's. users counts open leases; retired means a newer copy
      has replaced it, and it closes when users reaches 0. folder is None for a copy
      that is not this module's to delete (static, in tests).
    """
    con: duckdb.DuckDBPyConnection
    columns: ColumnTypes
    stages: frozenset[str]
    folder: Path | None = None
    built_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    users: int = 0
    retired: bool = False

    def close(self) -> None:
        """Close the connection and delete the folder. TECH: safe to call twice."""
        self.con.close()
        if self.folder is not None:
            shutil.rmtree(self.folder, ignore_errors=True)


def describe(con: duckdb.DuckDBPyConnection) -> ColumnTypes:
    """The copy's columns: name -> DuckDB type, in table order."""
    return {r[0]: r[1] for r in con.execute("DESCRIBE loans").fetchall()}


def build_snapshot(parquet_path: Path, stages: frozenset[str],
                   contributions: Mapping[str, Contribution]) -> TapeSnapshot:
    """Build a new copy: the tape plus every finished stage's columns, then read-only.

    TECH: stages are applied in workflow order (stages.STAGE_IDS); a finished stage
      with no contribution adds nothing. A failure deletes the half-built folder.
      The copy is built in an in-memory DuckDB and written to the file once, at the
      end (ATTACH the file, CREATE TABLE ... AS SELECT, DETACH): writing the tape to
      disk and then rewriting it with the stages' columns took about 3.3 s on 50,000
      loans, building in memory about 2.0 s (tests/test_slotting.py times it).
    """
    folder = Path(tempfile.mkdtemp(prefix="loaniq-agent-"))
    db_path = folder / "tape.duckdb"
    try:
        writer = duckdb.connect(":memory:")
        try:
            writer.execute("CREATE TABLE loans AS SELECT * FROM read_parquet(?)", [str(parquet_path)])
            for stage in STAGE_IDS:
                if stage in stages and stage in contributions:
                    contributions[stage](writer)
            writer.execute("ATTACH ? AS copy", [str(db_path)])
            writer.execute("CREATE TABLE copy.loans AS SELECT * FROM loans")
            writer.execute("DETACH copy")
        finally:
            writer.close()
        con = duckdb.connect(str(db_path), read_only=True, config=READ_ONLY_CONFIG)
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return TapeSnapshot(con=con, columns=describe(con), stages=stages, folder=folder)


class AgentTape:
    """The agent's current copy of the tape, swapped as stages finish.

    BUSINESS: one copy for every visitor, as the Loan Tape is one tape for everyone.
    TECH: see the module header. snapshot may be given (a fixed copy, for tests);
      otherwise the tape alone is built at once.
    """

    def __init__(self, parquet_path: Path | None, contributions: Mapping[str, Contribution] | None = None,
                 snapshot: TapeSnapshot | None = None) -> None:
        self.parquet_path = parquet_path
        self.contributions = dict(contributions or {})
        self._lock = threading.Lock()          # TECH: guards current and the lease counts
        self._build_lock = threading.Lock()    # TECH: one rebuild at a time
        self._threads: list[threading.Thread] = []
        if snapshot is None:
            if parquet_path is None:
                raise ValueError("AgentTape needs a Parquet path or a snapshot")
            snapshot = build_snapshot(parquet_path, frozenset({TAPE}), self.contributions)
        self._current = snapshot

    @classmethod
    def fixed(cls, con: duckdb.DuckDBPyConnection, columns: ColumnTypes | None = None,
              stages: frozenset[str] = frozenset({TAPE})) -> AgentTape:
        """A copy that never changes, around an existing connection (tests, scripts)."""
        return cls(None, snapshot=TapeSnapshot(con=con, columns=dict(columns or describe(con)), stages=stages))

    @property
    def stages(self) -> frozenset[str]:
        """BUSINESS: the stages the agent knows right now."""
        return self._current.stages

    @contextmanager
    def lease(self) -> Iterator[TapeSnapshot]:
        """Borrow the current copy for one tool call.

        TECH: the copy cannot be closed while leased; if it was replaced meanwhile,
          the last lease to end closes it.
        """
        with self._lock:
            snap = self._current
            snap.users += 1
        try:
            yield snap
        finally:
            with self._lock:
                snap.users -= 1
                done = snap.retired and snap.users == 0
            if done:
                snap.close()

    def rebuild(self, stages: frozenset[str]) -> TapeSnapshot:
        """Build a copy holding these stages and swap it in.

        BUSINESS: the agent learns a stage the moment the desk finishes it.
        TECH: building happens outside the swap lock, so queries keep running on the
          old copy meanwhile. The tape stage is always included.
        """
        if self.parquet_path is None:
            raise ValueError("A fixed AgentTape cannot be rebuilt")
        with self._build_lock:
            new = build_snapshot(self.parquet_path, frozenset(stages) | {TAPE}, self.contributions)
            with self._lock:
                old, self._current = self._current, new
                old.retired = True
                done = old.users == 0
            if done:
                old.close()
        return new

    def add_stage(self, stage: str) -> TapeSnapshot:
        """BUSINESS: a stage has published; rebuild the copy with it. TECH: synchronous."""
        return self.rebuild(self.stages | {stage})

    def add_stage_async(self, stage: str) -> threading.Thread:
        """add_stage on a background thread. TECH: wait() joins every such thread.

        BUSINESS: if the rebuild fails, the agent keeps the copy it had (it simply does
          not learn the stage yet) and the failure is logged.
        """
        def work() -> None:
            try:
                self.add_stage(stage)
            except Exception:  # noqa: BLE001 - a failed rebuild must never take the agent down
                log.exception("Rebuilding the agent's tape with stage %s failed", stage)
        thread = threading.Thread(target=work, name=f"agent-tape-{stage}", daemon=True)
        self._threads.append(thread)
        thread.start()
        return thread

    def wait(self, timeout_s: float | None = None) -> None:
        """TECH: wait for background rebuilds to finish (tests, shutdown)."""
        for thread in list(self._threads):
            thread.join(timeout_s)
        self._threads = [t for t in self._threads if t.is_alive()]

    def close(self) -> None:
        """Wait for rebuilds, then close the current copy and delete its folder."""
        self.wait()
        with self._lock:
            snap = self._current
            snap.retired = True
            done = snap.users == 0
        if done:
            snap.close()
