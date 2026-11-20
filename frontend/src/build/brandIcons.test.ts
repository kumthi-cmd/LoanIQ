/**
 * build/brandIcons.test.ts: tests for the plugin that publishes brand/icon/ at /icon/.
 *
 * BUSINESS: protects the rule that the brand kit is the only copy of the icons and
 *   reaches the app unchanged: every icon is published, byte for byte, at a fixed
 *   URL, and nothing else in brand/ (the README, the brand sheet) leaks out.
 * TECH: runs the plugin's hooks directly against the real brand/icon folder, with
 *   small fakes for Rollup's emitFile and for a dev-server request and response.
 */
import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { brandIconMiddleware, brandIcons, listBrandIcons } from "./brandIcons";

// TECH: node:path, not new URL(), because jsdom's URL class has no file: scheme.
const iconDir = resolve(dirname(fileURLToPath(import.meta.url)), "../../../brand/icon");

// BUSINESS: the files index.html and the web manifest name. If the kit drops one,
//   the browser tab or home-screen icon would break.
const REQUIRED = [
  "favicon.ico", "favicon.svg", "apple-touch-icon.png", "app-icon-192.png", "app-icon-512.png",
];

describe("listBrandIcons", () => {
  it("finds every icon the page and manifest link to", () => {
    expect(listBrandIcons(iconDir)).toEqual(expect.arrayContaining(REQUIRED));
  });

  it("fails loudly when the brand kit is missing", () => {
    expect(() => listBrandIcons(join(iconDir, "no-such-folder"))).toThrow();
  });
});

describe("brandIcons build hook", () => {
  it("writes every icon to icon/<name>, unhashed and byte for byte", () => {
    const emitted: { fileName: string; source: Uint8Array }[] = [];
    const plugin = brandIcons(iconDir);
    const hook = plugin.generateBundle as unknown as (this: unknown) => void;
    hook.call({ emitFile: (f: { fileName: string; source: Uint8Array }) => (emitted.push(f), f.fileName) });

    expect(emitted.map((f) => f.fileName)).toEqual(listBrandIcons(iconDir).map((n) => `icon/${n}`));
    const svg = emitted.find((f) => f.fileName === "icon/favicon.svg")!;
    expect(Buffer.from(svg.source).equals(readFileSync(join(iconDir, "favicon.svg")))).toBe(true);
  });
});

describe("brandIconMiddleware (dev server)", () => {
  /** TECH: run the handler once and record what it did. */
  function request(url: string) {
    const headers: Record<string, string> = {};
    let body: Buffer | null = null;
    const next = vi.fn();
    brandIconMiddleware(iconDir)(
      { url },
      { setHeader: (k, v) => { headers[k] = v; }, end: (b) => { body = b; } },
      next,
    );
    return { headers, body: body as Buffer | null, next };
  }

  it("serves an icon with its image type", () => {
    const res = request("/favicon.svg?v=1");
    expect(res.headers["Content-Type"]).toBe("image/svg+xml");
    expect(res.body?.equals(readFileSync(join(iconDir, "favicon.svg")))).toBe(true);
    expect(res.next).not.toHaveBeenCalled();
    expect(request("/favicon.ico").headers["Content-Type"]).toBe("image/x-icon");
  });

  // BUSINESS: only the icons are public; the rest of brand/ stays in the repo.
  it("passes unknown names and ../ paths on to the normal 404", () => {
    for (const url of ["/nope.png", "/../README.txt", "/..%2FREADME.txt", "/"]) {
      const res = request(url);
      expect(res.next).toHaveBeenCalledOnce();
      expect(res.body).toBeNull();
    }
  });
});
