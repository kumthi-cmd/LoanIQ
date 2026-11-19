# Architecture
LoanIQ follows the desk's flow:
loan tape -> slotting -> best execution -> position monitor and optimizer
-> pool candidates -> trade blotter.

| Part | Step | What it does |
| --- | --- | --- |
| Loan tape | 1 | Synthetic tape from `backend/app/loan_tape_gen.py` (config in `backend/app/config/loan_tape_gen.toml`), written to `data/loan_tape.parquet` and `.csv`, loaded into DuckDB in memory. Fields: `docs/domain/loan-tape-schema.md` |
| Loan API | 1 | FastAPI: paged, sorted and filtered loans |
| SPA | 1 | React screens; explanations rendered from content/ |
| Parser | 2 | Maps and cleans seller tapes |
| Ask the Tape | 4 | Claude agent with read-only tools |
| Slotting | 5 | Story tags from the validated rules in `backend/app/config/spec_stories.toml` (loaded by `backend/app/spec_stories.py`, Step 1a); down and up coupon from the note rate |
| Best execution | 6 | Prices every slot from the price file |
| Blotter and positions | 7 | Trades, P&L, DV01, limits |
| Optimizer | 8 | MILP that maximizes proceeds at price; outputs pool candidates |

Update this file when a part is added or changes.
