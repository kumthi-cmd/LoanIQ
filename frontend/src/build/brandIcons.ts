/**
 * build/brandIcons.ts: a small Vite plugin that publishes brand/icon/ at /icon/.
 *
 * Where it sits: brand/icon/ (the logo kit, the only copy) -> [this plugin] ->
 *   /icon/* in the dev server and frontend/dist/icon/* in the build -> served by
 *   FastAPI like any other file in dist. vite.config.ts registers it.
 *
 * BUSINESS: the browser tab, bookmarks and a phone's home screen show the LoanIQ
 *   Labs flask. The brand kit stays in one place (brand/), so a new version of the
 *   artwork reaches the app with no copying and nothing to forget.
 * TECH:
 *   - Favicons need fixed, unhashed URLs (/icon/favicon.svg), because index.html
 *     and the web manifest name them directly and browsers ask for them by name.
 *     An import alias (like "@content") would give them hashed names, so it is not
 *     used here. The header logo, which the code imports, does use an alias.
 *   - Vite's own publicDir is not pointed at brand/, because that would also
 *     publish brand/README.txt and the large brand-sheet.png.
 *   - A Vite plugin is an object with hook functions. configureServer runs once
 *     when the dev server starts; generateBundle runs once at the end of a build.
 *   - Only files actually listed in brand/icon/ are served, so a URL such as
 *     /icon/../README.txt can never reach another file.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { extname, join } from "node:path";
import type { Plugin } from "vite";

/** TECH: Content-Type for each icon file type, so browsers accept them in dev. */
const MIME_TYPES: Record<string, string> = {
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
};

/**
 * The icon files to publish, by name.
 * BUSINESS: every favicon and app icon in the brand kit, exactly as delivered.
 * TECH: plain files directly in iconDir, sorted for a stable order. Folders are
 *   skipped. Throws if iconDir does not exist, so a missing brand kit fails the
 *   build loudly instead of shipping an app with no icons.
 */
export function listBrandIcons(iconDir: string): string[] {
  return readdirSync(iconDir)
    .filter((name) => statSync(join(iconDir, name)).isFile())
    .sort();
}

/** TECH: the slice of Node's request and response that the dev middleware uses. */
interface DevRequest { url?: string }
interface DevResponse { setHeader(name: string, value: string): void; end(body: Buffer): void }

/**
 * Build the dev-server handler for /icon/<name>.
 * BUSINESS: in `npm run dev` the favicon shows up just as it does in the build.
 * TECH: Vite's dev server uses "connect" middleware. When a handler is mounted at
 *   "/icon", connect strips that prefix, so req.url here is "/favicon.svg". Any name
 *   not in the icon list (including "../" tricks) goes to next(), the usual 404.
 */
export function brandIconMiddleware(iconDir: string) {
  return (req: DevRequest, res: DevResponse, next: () => void) => {
    // TECH: drop any query string (?v=2) and the leading slash.
    const name = decodeURIComponent((req.url ?? "").split("?")[0].replace(/^\//, ""));
    if (!listBrandIcons(iconDir).includes(name)) {
      next();
      return;
    }
    res.setHeader("Content-Type", MIME_TYPES[extname(name)] ?? "application/octet-stream");
    res.end(readFileSync(join(iconDir, name)));
  };
}

/** TECH: the slice of Rollup's plugin context that generateBundle uses. */
interface EmitContext {
  emitFile(file: { type: "asset"; fileName: string; source: Uint8Array }): string;
}

/**
 * The Vite plugin.
 * BUSINESS: publishes the brand kit's icons with the app, unchanged.
 * TECH: iconDir is an absolute path to brand/icon. urlDir is the folder they appear
 *   under (default "icon", giving /icon/favicon.svg). In the build, emitFile with a
 *   fixed fileName writes each file into dist/icon/ with no hash in its name.
 */
export function brandIcons(iconDir: string, urlDir = "icon"): Plugin {
  return {
    name: "loaniq-brand-icons",
    configureServer(server) {
      server.middlewares.use(`/${urlDir}`, brandIconMiddleware(iconDir));
    },
    generateBundle(this: EmitContext) {
      for (const name of listBrandIcons(iconDir)) {
        this.emitFile({ type: "asset", fileName: `${urlDir}/${name}`, source: readFileSync(join(iconDir, name)) });
      }
    },
  };
}
