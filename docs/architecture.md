# Architecture
LoanIQ follows the desk's flow:
loan tape -> slotting -> best execution -> position monitor and optimizer
-> pool candidates -> trade blotter.

| Part | Step | What it does |
| --- | --- | --- |
| Loan tape | 1 | Synthetic tape in Parquet, loaded into DuckDB in memory |
| Loan API | 1 | FastAPI: paged, sorted and filtered loans |
| SPA | 1 | React screens; explanations rendered from content/ |
| Parser | 2 | Maps and cleans seller tapes |
| Ask the Tape | 4 | Claude agent with read-only tools |
| Slotting | 5 | Story tags; down and up coupon from the note rate |
| Best execution | 6 | Prices every slot from the price file |
| Blotter and positions | 7 | Trades, P&L, DV01, limits |
| Optimizer | 8 | MILP that maximizes proceeds at price; outputs pool candidates |

Update this file when a part is added or changes.
