/**
 * playwright.config.ts: end-to-end test settings for LoanIQ.
 *
 * Where it sits: test.ps1 builds the SPA (frontend/dist) -> [Playwright] starts
 * FastAPI, which serves the SPA and the API at http://localhost:8000 -> a real
 * Chromium browser clicks through the screens.
 *
 * BUSINESS: tests what a visitor really does: open the Loan Tape, sort, filter,
 *   read a number, open the explanation.
 * TECH:
 *   - webServer: Playwright starts uvicorn itself and waits for /api/health.
 *     reuseExistingServer is false so a test never depends on a server you started
 *     (.claude/rules/e2e.md); if port 8000 is busy, the run stops with an error.
 *   - The server reads the default seeded tape (data/loan_tape.parquet, generated
 *     on first start), so the loans are the same on every run. Tests still read
 *     expected numbers from the API rather than hard-coding them.
 *   - One worker: all tests share one server and its in-memory tape.
 *   - The SPA must be built first (npm run build in frontend/); test.ps1 does that.
 *   - ANTHROPIC_API_KEY is blanked for the test server (Step 4b), so Ask the Tape is
 *     always answered by the built-in rules: free, repeatable, and never dependent
 *     on a key someone has set in their shell. The live model is measured by
 *     backend/scripts/eval_agent.py instead.
 */
import { defineConfig, devices } from "@playwright/test";

const isWindows = process.platform === "win32";
const python = isWindows ? ".venv\\Scripts\\python.exe" : ".venv/bin/python";

export default defineConfig({
  testDir: "./tests",
  outputDir: "./test-results",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 30_000,
  reporter: [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  use: {
    baseURL: "http://localhost:8000",
    trace: "retain-on-failure",
  },
  // TECH: Product Slotting (Step 5b) changes the shared server's tape for every test
  //   after it (two new columns, a shared result). So its spec is a project of its
  //   own that depends on the main one: Playwright runs it only after every other
  //   test has finished, on the same server.
  projects: [
    { name: "chromium", testIgnore: /product-slotting\.spec\.ts/,
      use: { ...devices["Desktop Chrome"], viewport: { width: 1600, height: 900 } } },
    { name: "slotting", testMatch: /product-slotting\.spec\.ts/, dependencies: ["chromium"],
      use: { ...devices["Desktop Chrome"], viewport: { width: 1600, height: 900 } } },
  ],
  webServer: {
    command: `${python} -m uvicorn app.main:app --port 8000`,
    cwd: "../backend",
    url: "http://localhost:8000/api/health",
    reuseExistingServer: false,
    // TECH: added to the server's environment; an empty key switches the model off.
    env: { ANTHROPIC_API_KEY: "" },
    timeout: 120_000,
  },
});
