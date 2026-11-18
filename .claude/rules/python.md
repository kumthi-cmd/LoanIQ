---
paths:
  - "backend/**"
---
# Python back end
- Python 3.12 in backend/.venv. Dependencies in backend/requirements.txt.
- Type hints on every function. Pydantic models for every API request and response.
- Money in Decimal or integer cents in calculations. Rates in percent with 3 decimals.
- DuckDB: always pass values as parameters, and check column names against the real list.
- Thresholds, limits and price grids live in config files, not in code.
- Keep functions short enough to read on one screen.
