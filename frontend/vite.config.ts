/**
 * vite.config.ts: build, dev-server and unit-test settings for the LoanIQ SPA.
 *
 * Where it sits: frontend/ (this) -> npm run build -> frontend/dist -> served by
 * FastAPI at http://localhost:8000. In dev mode (npm run dev) Vite serves the SPA
 * on http://localhost:5173 and forwards /api to FastAPI.
 *
 * BUSINESS: one app, two ways to run it. Dev mode reloads the screen as code
 *   changes; the build is what a visitor (and Playwright) sees.
 * TECH:
 *   - server.proxy: requests to /api go to FastAPI on port 8000, so the SPA calls
 *     the same relative URLs (/api/loans) in dev and in the build, with no CORS setup.
 *   - The "@content" alias points at ../content, where visitor-facing words live
 *     (.claude/rules/showcase.md). server.fs.allow lets the dev server read it.
 *   - test: Vitest settings. jsdom is a simulated browser for component tests;
 *     globals makes describe/it/expect available without imports.
 */
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const contentDir = fileURLToPath(new URL("../content", import.meta.url));
const repoRoot = fileURLToPath(new URL("..", import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@content": contentDir } },
  build: {
    // TECH: Vite warns above 500 kB per JavaScript file. LoanIQ registers AG Grid's
    //   AllCommunityModule (every free grid feature), which alone is most of the
    //   ~1.6 MB bundle (~480 kB gzipped). For a desk app loaded once and then cached,
    //   that is acceptable; the limit is set just above it so real growth still warns.
    //   Registering only the AG Grid modules we use would shrink it, if it ever matters.
    chunkSizeWarningLimit: 1800,
  },
  server: {
    proxy: { "/api": "http://localhost:8000" },
    fs: { allow: [repoRoot] },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
  },
});
