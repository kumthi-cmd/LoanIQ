"""The agent's own read-only copy of the tape: a DuckDB file nothing can write to.

Where it sits:
    data/loan_tape.parquet -> [tape_db.open_readonly_tape] -> tools.query_tape

BUSINESS: the model's queries run against a copy of the tape that is read-only at
  the database level. Even if a query got past the SQL checks, it could not change
  the tape the grid shows, write a file, or read anything else on the server.
TECH:
  - The grid's tape is an in-memory DuckDB database, and DuckDB cannot open an
    in-memory database read-only. So at start-up the Parquet tape is copied once
    into a DuckDB file in a fresh temporary folder (about 1 MB for 2,000 loans), and
    that file is opened with read_only=True.
  - enable_external_access=False stops read_csv, read_parquet, COPY ... TO and
    ATTACH from touching the file system or the network. lock_configuration=True
    stops any SET statement from switching it back on.
  - The temporary folder is new for every start, so a stale copy can never be read;
    close_readonly_tape() deletes it at shutdown.
  - The copy is the seller's tape only. Product slotting (Step 5a) runs later, on
    demand, on the grid's store, so the agent does not see slot columns yet
    (docs/roadmap.md lists it as a follow-up).
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

import duckdb


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
    con = duckdb.connect(str(db_path), read_only=True,
                         config={"enable_external_access": False, "lock_configuration": True})
    return ReadOnlyTape(con=con, folder=folder)


def close_readonly_tape(tape: ReadOnlyTape) -> None:
    """Close the connection and delete the temporary folder. TECH: safe to call twice."""
    tape.con.close()
    shutil.rmtree(tape.folder, ignore_errors=True)
