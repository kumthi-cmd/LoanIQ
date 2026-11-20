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
 *   - The "@brand" alias points at ../brand, the LoanIQ Labs logo kit (the only
 *     copy; see brand/README.txt). Code imports the logo it shows from there, and
 *     Vite publishes just that file, with a hashed name, under assets/.
 *   - brandIcons() publishes brand/icon/ at /icon/ with fixed names, because
 *     index.html and public/site.webmanifest link to the favicons by URL
 *     (src/build/brandIcons.ts explains why an alias cannot do that).
 *   - public/ (Vite's default publicDir) holds site.webmanifest, copied as-is to
 *     the root of dist.
 *   - test: Vitest settings. jsdom is a simulated browser for component tests;
 *     globals makes describe/it/expect available without imports.
 */
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";
import { brandIcons } from "./src/build/brandIcons.ts";

const contentDir = fileURLToPath(new URL("../content", import.meta.url));
const brandDir = fileURLToPath(new URL("../brand", import.meta.url));
const brandIconDir = fileURLToPath(new URL("../brand/icon", import.meta.url));
const repoRoot = fileURLToPath(new URL("..", import.meta.url));

export default defineConfig({
  plugins: [react(), brandIcons(brandIconDir)],
  resolve: { alias: { "@content": contentDir, "@brand": brandDir } },
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
