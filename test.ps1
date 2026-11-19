<#
test.ps1: run every LoanIQ test layer, in order, and stop at the first failure.

BUSINESS: nothing is shown to a visitor (start.ps1) or committed unless every layer
  passes: the business rules in the back end, the screens in the front end, and
  what a visitor does in a real browser.
TECH: from the repo root:  .\test.ps1
  1. Back end:  pytest with coverage; fails under 80% (.claude/rules/testing.md).
  2. Front end: TypeScript type check, Vitest unit and component tests.
  3. Build:     npm run build writes frontend/dist, the SPA FastAPI serves.
  4. End to end: Playwright starts FastAPI on port 8000 itself and clicks through
     the built app in Chromium. Port 8000 must be free (stop any dev server first).
  Missing node_modules are installed with `npm ci` (exact versions from the lock
  file). The script exits with 1 on any failure, so start.ps1 can refuse to start.
#>
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

# TECH: run one step in a folder; stop the whole script if its exit code is not 0.
#   The exit code is the only pass/fail signal. Tools like Vite and npm print
#   warnings on stderr, and Windows PowerShell 5.1 would turn those into errors under
#   "Stop", so native commands run under "Continue" here.
function Invoke-Step([string]$Name, [string]$Folder, [scriptblock]$Command) {
    Write-Host "`n=== $Name ===" -ForegroundColor Cyan
    Push-Location (Join-Path $root $Folder)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $Command
        if ($LASTEXITCODE -ne 0) { throw "$Name failed (exit code $LASTEXITCODE)" }
    } finally {
        $ErrorActionPreference = $previous
        Pop-Location
    }
}

# TECH: install a Node project's packages only when they are missing.
function Install-NodePackages([string]$Folder) {
    if (-not (Test-Path (Join-Path $root "$Folder\node_modules"))) {
        Invoke-Step "Install $Folder packages" $Folder { npm ci }
    }
}

try {
    Invoke-Step "Back end: pytest with coverage (80% minimum)" "backend" {
        .venv\Scripts\python.exe -m pytest --cov=app --cov-report=term-missing:skip-covered --cov-fail-under=80
    }
    Install-NodePackages "frontend"
    Invoke-Step "Front end: type check" "frontend" { npm run typecheck }
    Invoke-Step "Front end: Vitest" "frontend" { npx vitest run }
    Invoke-Step "Front end: build" "frontend" { npm run build }
    Install-NodePackages "e2e"
    Invoke-Step "End to end: Playwright" "e2e" { npx playwright test }
} catch {
    Write-Host "`nTESTS FAILED: $_" -ForegroundColor Red
    exit 1
}
Write-Host "`nAll test layers passed." -ForegroundColor Green
exit 0
