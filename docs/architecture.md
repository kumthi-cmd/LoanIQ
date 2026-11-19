# Architecture
LoanIQ follows the desk's flow:
loan tape -> slotting -> best execution -> position monitor and optimizer
-> pool candidates -> trade blotter.

| Part | Step | What it does |
| --- | --- | --- |
| Loan tape | 1 | Synthetic tape from `backend/app/loan_tape_gen.py` (config in `backend/app/config/loan_tape_gen.toml`), written to `data/loan_tape.parquet` and `.csv`, loaded into DuckDB in memory. Fields: `docs/domain/loan-tape-schema.md` |
| Loan API | 1 | FastAPI in `backend/app/main.py` (Step 1b): health, columns, paged loans and a UPB-weighted summary. SQL for sorting and AG Grid filters built safely in `backend/app/loan_query.py`; limits in `backend/app/config/api.toml`; column labels in `content/loan-columns.json` |
| SPA | 1 | `frontend/` (Step 1c): Vite, React, TypeScript, React Router and AG Grid Community. Loan Tape screen at `/`: KPI tiles from `/api/loans/summary`, a grid on the Infinite Row Model paging `/api/loans` 100 loans at a time with server-side sort and filter. API types generated from FastAPI's OpenAPI spec (`backend/app/export_openapi.py`, `npm run gen:api`). Explanations and glossary tooltips read from `content/`. Built into `frontend/dist` and served by FastAPI at `/` |
| Parser | 2 | Maps and cleans seller tapes |
| Ask the Tape | 4 | Claude agent with read-only tools |
| Slotting | 5 | Story tags from the validated rules in `backend/app/config/spec_stories.toml` (loaded by `backend/app/spec_stories.py`, Step 1a); down and up coupon from the note rate |
| Best execution | 6 | Prices every slot from the price file |
| Blotter and positions | 7 | Trades, P&L, DV01, limits |
| Optimizer | 8 | MILP that maximizes proceeds at price; outputs pool candidates |

## Running it
- Everything, tested first: `.\start.ps1` from the repo root, then http://localhost:8000.
  It runs `.\test.ps1` (pytest, type check, Vitest, build, Playwright) and starts only if all pass.
- Dev mode, two terminals:
  1. API: in `backend\`, `.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000 --reload`
  2. SPA: in `frontend\`, `npm run dev`, then http://localhost:5173. Vite proxies `/api` to port 8000.
- After changing an API model: in `backend\`, `.venv\Scripts\python.exe -m app.export_openapi`,
  then in `frontend\`, `npm run gen:api`.

Update this file when a part is added or changes.
