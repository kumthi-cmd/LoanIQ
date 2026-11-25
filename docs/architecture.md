# Architecture
LoanIQ follows the desk's flow:
loan tape -> slotting -> best execution -> position monitor and optimizer
-> pool candidates -> trade blotter.

| Part | Step | What it does |
| --- | --- | --- |
| Loan tape | 1 | Synthetic tape from `backend/app/loan_tape_gen.py` (config in `backend/app/config/loan_tape_gen.toml`), written to `data/loan_tape.parquet` and `.csv`, loaded into DuckDB in memory. Fields: `docs/domain/loan-tape-schema.md` |
| Loan API | 1 | FastAPI in `backend/app/main.py` (Step 1b): health, columns, paged loans and a UPB-weighted summary. SQL for sorting and AG Grid filters built safely in `backend/app/loan_query.py`; limits in `backend/app/config/api.toml`; column labels in `content/loan-columns.json`. Screen panels (`/api/loans/breakdowns`, `/api/loans/questions`, `/api/tape`) in `backend/app/tape_panels.py`; desk-question rules in `backend/app/config/desk_questions.toml`, validated by `backend/app/desk_questions.py` and applied with `/api/loans?question=<id>` |
| SPA | 1 | `frontend/` (Step 1c, redesigned to the "1 · Loan Tape" board): Vite, React, TypeScript, React Router and AG Grid Community. Loan Tape screen at `/`: KPI tiles from `/api/loans/summary`, three panels (program mix and MBA delinquency from `/api/loans/breakdowns`; since Step 5b Slotting, in place of note-rate buckets, from `/api/slotting/status`), desk-question chips from `/api/loans/questions`, and a grid on the Infinite Row Model paging `/api/loans` 100 loans at a time with server-side sort, filter and question. API types generated from FastAPI's OpenAPI spec (`backend/app/export_openapi.py`, `npm run gen:api`). Explanations and glossary tooltips read from `content/`. Showcase pages (Step 1f): About at `/about` (`content/about.md` under the stacked logo) and How it was built at `/how-it-was-built` (`content/how-it-was-built.md`, "By the numbers" from `content/build-facts.json`, written by `test.ps1` after every layer passes, then `content/build-log.md`). Built into `frontend/dist` and served by FastAPI at `/` |
| Parser | 2 | Maps and cleans seller tapes |
| Ask the Tape | 4 | Design: `content/agent.md`. Engine (Step 4a) in `backend/app/agent/`: `orchestrator.py` runs the loop (5 rounds, 800 output tokens per call, 20 s) over five tools in `tools.py` (`list_columns`, `query_tape`, `summarize_tape`, `lookup_term`, `get_loan`). `query_tape` SQL is checked by `sql_guard.py` (sqlglot allowlist, named bound parameters, 500-row cap, 2 s timeout) and runs on a read-only DuckDB copy of the tape (`tape_db.py`); full results are kept by query id (`query_store.py`). Models behind one interface in `providers/` (Anthropic live, Offline rules, Fake for tests, OpenAI and Gemini off until a key is set). Models, limits, prices, budget and offline rules in `backend/app/config/llm.toml`; cost, daily cap and per-visitor limit in `budget.py`; system prompt `system_prompt.md`; visitor-facing words in `content/ask-the-tape.json`. Routes in `api.py`: `POST /api/ask` (Server-Sent Events) and `GET /api/ask/queries/{id}`; from Step 4b also `GET /api/ask/status` (model or built-in rules), `GET /api/ask/loans/{id}` (the `get_loan` tool, for the loan drawer) and `POST /api/ask/rerun` (a saved query's SQL through the same guard, no model). Each query result carries its Loan Tape link (`loan_tape_link.py`: WHERE and ORDER BY -> AG Grid filter model and sort). A failed model call logs the provider's status and message, redacted (`providers/base.py` `sdk_error`). Golden questions in `backend/evals/golden_questions.toml`, graded by `golden.py`; run live with `backend/scripts/eval_agent.py`. Screen (Step 4b): `frontend/src/screens/AskTheTapeScreen.tsx` with `components/ask/` and `ask/` (SSE reader, turn model, saved queries in localStorage, Loan Tape URL); the Loan Tape reads `?filter=`, `?sort=` and `?question=` from its URL; the header box and Ctrl K open `/ask?q=`. Words in `content/ask-the-tape.json` ("screen") and `content/screens/ask-the-tape.md` |
| Slotting | 5 | A Loan Tape feature, not a screen. Engine (Step 5a) in `backend/app/slotting.py`: rules in `backend/app/config/slotting.toml` (agency map, TBA products, eligible status, coupon rule), checked at start-up; spec stories from `backend/app/config/spec_stories.toml`. A run is one pass in DuckDB that writes a `slots` table (loan_id, eligible, reason, agency, term, down and up coupons, stories, and the grid text `slot` and `spec_stories`), then counts each step from it and publishes in one transaction; the Loan Tape then pages the view `loans_slotted` (the tape plus Slot and Spec Stories). Routes in `backend/app/slotting_api.py`: `POST /api/slotting/run` (Server-Sent Events: one `step` event per step, 13 today, then `done` with the totals; no server-side pauses), `GET /api/slotting/status` (last run time and totals, or not run) and `GET /api/loans/{loan_id}/slots` (the hover card). One shared result for every visitor, in memory, behind a lock (a second run gets HTTP 409). Ask the Tape's copy stays the seller's tape. Words in `content/slotting.json`; rules explained in `docs/domain/slotting-rules.md`. Screen (Step 5b): the sidebar's Product Slotting button (`components/SlottingNavButton.tsx`, `nav.ts` action) opens `components/SlottingDialog.tsx` (confirm, the run's commentary paced by `slotting/slottingConfig.ts`, done) from any screen; state in `slotting/SlottingContext.tsx` (status, the stream from `slotting/slottingStream.ts`, the `slotting/runState.ts` reducer). On the Loan Tape: `components/SlottingPanel.tsx` (in place of the note-rate panel), `components/SlottingNotice.tsx`, Slot and Spec Stories cells (`grid/SlotCell.tsx`, `grid/SpecStoriesCell.tsx`) and the hover card (`grid/LoanIdCell.tsx` -> `components/SlotCard.tsx`). Words in the "screen" section of `content/slotting.json`; explanation in `content/screens/product-slotting.md`, offered by the Loan Tape's Explain panel switch |
| Best execution | 6 | Prices every slot from the price file |
| Blotter and positions | 7 | Trades, P&L, DV01, limits |
| Optimizer | 8 | MILP that maximizes proceeds at price; outputs pool candidates |
| Hosting | Hosting | One Docker container (`Dockerfile`), tested by GitHub Actions (`.github/workflows/ci.yml`) and deployed by Render (`render.yaml`). See "Hosting" below |

## Hosting
LoanIQ runs as one service in production, the same way it runs locally and in the
Playwright tests: FastAPI serves the built SPA at `/` and the API at `/api`. One
address means no CORS and, from Step 4, the Claude API key stays on the server.

    git push -> GitHub Actions: tests -> container -> (main only) Render: build -> health check -> live

- Container: `Dockerfile` at the repo root, built from the repo root (Vite reads
  `../content` and `../brand`). Stage 1 builds the SPA with Node (version in `.nvmrc`);
  stage 2 runs it on Python 3.12 with `backend/`, `content/` and `frontend/dist` in the
  repo's layout under `/app`. The seeded tape is generated when the image is built
  (`data/` is not in Git), so every deploy serves the same loans. Runs as a non-root
  user on `$PORT`. `.dockerignore` keeps secrets, venvs, `node_modules` and local data out.
  Portable: only `render.yaml` is host-specific.
- CI: `.github/workflows/ci.yml` on every push and on pull requests into `main`. Job
  `tests` mirrors `test.ps1` layer for layer; job `container` builds the image, runs
  it and checks `/api/health` and `/`. A newer push cancels the older run on the same
  branch.
- Render: `render.yaml` (a Blueprint) defines one web service that deploys `main` only
  after every check passes, and switches traffic only once `/api/health` answers.
  Plan, region and settings live in that file.
- Domain: live at https://www.loaniqlabs.com (registered at Namecheap; docs/roadmap.md).
- Checks without Docker: `backend/tests/test_deploy_config.py` reads the Dockerfile,
  `.dockerignore`, `ci.yml` and `render.yaml` and fails if they drift from the app
  or from `test.ps1`.

## Running it
- Everything, tested first: `.\start.ps1` from the repo root, then http://localhost:8000.
  It runs `.\test.ps1` (pytest, type check, Vitest, build, Playwright) and starts only if all pass.
  After a green run, `test.ps1` also rewrites `content/build-facts.json`; commit it.
- Dev mode, two terminals:
  1. API: in `backend\`, `.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000 --reload`
  2. SPA: in `frontend\`, `npm run dev`, then http://localhost:5173. Vite proxies `/api` to port 8000.
- After changing an API model: in `backend\`, `.venv\Scripts\python.exe -m app.export_openapi`,
  then in `frontend\`, `npm run gen:api`.

Update this file when a part is added or changes.
