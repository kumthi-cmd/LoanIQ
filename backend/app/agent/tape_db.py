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
  - From Step 5a the copy is slotted exactly like the grid's tape
    (slotting.create_slotted_table), so the model can ask about slot_product,
    base_coupon and the other slot columns the grid lists.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

import duckdb

from app.slotting import SlottingRules, create_slotted_table, load_slotting_rules, parquet_columns


@dataclass
class ReadOnlyTape:
    """The read-only connection and the folder holding its file.

    TECH: con is shared by all agent requests; each tool call takes its own cursor.
    """
    con: duckdb.DuckDBPyConnection
    folder: Path


def open_readonly_tape(parquet_path: Path, rules: SlottingRules | None = None) -> ReadOnlyTape:
    """Copy the Parquet tape, slotted, into a new DuckDB file and open it read-only.

    BUSINESS: the agent sees the same loans and the same slots as the grid.
    TECH: rules default to config/slotting.toml, checked against this tape's
      columns. The write connection is closed before the read-only one opens;
      DuckDB allows only one writer, and none is needed after the copy.
    """
    folder = Path(tempfile.mkdtemp(prefix="loaniq-agent-"))
    db_path = folder / "tape.duckdb"
    writer = duckdb.connect(str(db_path))
    try:
        rules = rules or load_slotting_rules(parquet_columns(writer, parquet_path))
        create_slotted_table(writer, parquet_path, rules)
    finally:
        writer.close()
    con = duckdb.connect(str(db_path), read_only=True,
                         config={"enable_external_access": False, "lock_configuration": True})
    return ReadOnlyTape(con=con, folder=folder)


def close_readonly_tape(tape: ReadOnlyTape) -> None:
    """Close the connection and delete the temporary folder. TECH: safe to call twice."""
    tape.con.close()
    shutil.rmtree(tape.folder, ignore_errors=True)
