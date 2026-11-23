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
  When all four pass, Write-BuildFacts writes content/build-facts.json (test counts,
  coverage, commits, date) for the How it was built page. Commit that file.
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

# BUSINESS: the "By the numbers" facts on the How it was built page: how many tests
#   guard each layer, back-end coverage, and how many commits it took. Written only
#   after every layer has passed, so the page never shows numbers from a failing run.
#   Commit content/build-facts.json; the hosted site shows the last committed copy.
# TECH: a plain function, NOT an Invoke-Step: backend/tests/test_deploy_config.py
#   counts exactly five Invoke-Step layers and checks ci.yml runs the same ones.
#   Nothing is re-run; each number comes from a quick listing or a file the layers
#   left behind:
#     back-end tests   pytest --collect-only -q   ("226 tests collected")
#     coverage         coverage report --format=total --precision=1, from the
#                      backend/.coverage file pytest-cov wrote (percent, e.g. 98.8)
#     front-end tests  frontend/test-results/vitest.json (numTotalTests), written
#                      by the Vitest layer's JSON reporter (vite.config.ts explains
#                      why not `vitest list`)
#     e2e tests        playwright test --list     ("Total: 14 tests in 1 file")
#     commits          git rev-list --count HEAD (before this run's own commit)
#   A number that cannot be read is left out with a warning: the page shows a dash,
#   and a passing run is never failed by its own bookkeeping.
#   The file is UTF-8 without a byte-order mark (Windows PowerShell 5.1's Out-File
#   would add one) and with "\n" line endings, so it diffs cleanly in Git.
function Write-BuildFacts([datetime]$RunStarted) {
    Write-Host "`n=== Build facts: content/build-facts.json ===" -ForegroundColor Cyan
    $facts = [ordered]@{}

    # TECH: run a native command and return its output lines; never throw. Under
    #   "Continue", stderr warnings from npm or Python don't become errors.
    function Get-Lines([string]$Folder, [scriptblock]$Command) {
        Push-Location (Join-Path $root $Folder)
        $previous = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        try { return @(& $Command 2>$null) } catch { return @() }
        finally { $ErrorActionPreference = $previous; Pop-Location }
    }
    # TECH: first capture group of the first line matching $Pattern, as a number.
    function Find-Number([string[]]$Lines, [string]$Pattern) {
        foreach ($line in $Lines) {
            if ($line -match $Pattern) { return [double]::Parse($Matches[1], [Globalization.CultureInfo]::InvariantCulture) }
        }
        return $null
    }

    # TECH: one fact per line. --collect-only lists tests without running them and,
    #   with no --cov flag, leaves the .coverage file from the pytest layer untouched.
    $facts.backendTests = Find-Number (Get-Lines "backend" { .venv\Scripts\python.exe -m pytest --collect-only -q }) '^(\d+) tests? collected'
    $facts.frontendTests = $null
    $vitestJson = Join-Path $root "frontend\test-results\vitest.json"
    # TECH: only a report written by this run counts; an older file would be stale.
    if ((Test-Path $vitestJson) -and (Get-Item $vitestJson).LastWriteTime -ge $RunStarted) {
        try { $facts.frontendTests = [double](Get-Content $vitestJson -Raw | ConvertFrom-Json).numTotalTests } catch {}
    }
    $facts.e2eTests = Find-Number (Get-Lines "e2e" { npx playwright test --list }) '^Total: (\d+) tests?'
    $facts.backendCoverage = Find-Number (Get-Lines "backend" { .venv\Scripts\python.exe -m coverage report --format=total --precision=1 }) '^(\d+(?:\.\d+)?)$'
    $facts.commits = Find-Number (Get-Lines "." { git rev-list --count HEAD }) '^(\d+)$'

    # TECH: build the JSON by hand: integers without ".0", coverage with one decimal,
    #   invariant culture so a comma-decimal Windows locale cannot write "98,8".
    $inv = [Globalization.CultureInfo]::InvariantCulture
    $lines = @()
    foreach ($key in @("backendTests", "frontendTests", "e2eTests", "backendCoverage", "commits")) {
        $value = $facts[$key]
        if ($null -eq $value) { Write-Host "WARNING: could not read $key; left out" -ForegroundColor Yellow; continue }
        $text = if ($key -eq "backendCoverage") { $value.ToString("0.0", $inv) } else { $value.ToString("0", $inv) }
        $lines += "  `"$key`": $text"
    }
    $lines += "  `"date`": `"$($RunStarted.ToString('yyyy-MM-dd', $inv))`""
    $json = "{`n" + ($lines -join ",`n") + "`n}`n"
    $path = Join-Path $root "content\build-facts.json"
    [IO.File]::WriteAllText($path, $json, (New-Object Text.UTF8Encoding($false)))
    Write-Host $json.TrimEnd()
}

$runStarted = Get-Date
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
# TECH: after the try/catch, so it only runs when all five layers passed.
Write-BuildFacts $runStarted
Write-Host "`nAll test layers passed." -ForegroundColor Green
exit 0
