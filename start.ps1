<#
start.ps1: test everything, then start LoanIQ at http://localhost:8000.

BUSINESS: the app a visitor sees has always passed every test first.
TECH: from the repo root:  .\start.ps1
  Runs test.ps1 (which also builds the SPA into frontend/dist). Only if every layer
  passes does it start FastAPI with uvicorn, which serves the built SPA at "/" and
  the API under /api. Stop the server with Ctrl+C.
  For day-to-day front-end work use dev mode instead (two terminals, see
  docs/architecture.md): uvicorn for the API and `npm run dev` for the SPA.
#>
$root = $PSScriptRoot

& (Join-Path $root "test.ps1")
if ($LASTEXITCODE -ne 0) {
    Write-Host "LoanIQ not started: fix the failing tests first." -ForegroundColor Red
    exit 1
}

Write-Host "`nStarting LoanIQ at http://localhost:8000 (Ctrl+C to stop)" -ForegroundColor Green
Push-Location (Join-Path $root "backend")
try {
    .venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
} finally {
    Pop-Location
}
