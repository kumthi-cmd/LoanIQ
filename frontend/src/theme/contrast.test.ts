/**
 * theme/contrast.test.ts: every text colour in styles.css is readable on its background.
 *
 * BUSINESS: protects legibility on the desk screen, including the synthetic-data
 *   warning and the brand colours added in Step 1e. If someone darkens a background
 *   or dims the muted grey, this fails before a visitor squints.
 * TECH: reads styles.css from disk and checks each text-on-background pair the page
 *   uses against WCAG AA. It reads the file with Node's fs rather than a "?raw"
 *   import, because the Vitest config sets css: false, which turns every CSS import
 *   (raw ones included) into an empty string. Paths are built with node:path, not
 *   new URL(), because jsdom replaces URL with a version that has no file: scheme.
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { WCAG_AA_TEXT, contrastRatio, luminance, readColorTokens } from "./contrast";

const here = dirname(fileURLToPath(import.meta.url));
const t = readColorTokens(readFileSync(resolve(here, "../styles.css"), "utf8"));

describe("contrast arithmetic", () => {
  // TECH: the WCAG end points, so the formula itself is pinned down.
  it("gives 21:1 for black on white and 1:1 for a colour on itself", () => {
    expect(contrastRatio("#000000", "#ffffff")).toBeCloseTo(21, 5);
    expect(contrastRatio("#0b111b", "#0b111b")).toBe(1);
    expect(contrastRatio("#ffffff", "#000000")).toBe(contrastRatio("#000000", "#ffffff"));
  });

  it("rejects colours it cannot read instead of passing them", () => {
    expect(() => luminance("#fff")).toThrow();
    expect(() => luminance("gold")).toThrow();
  });
});

describe("styles.css text contrast (WCAG AA, 4.5:1)", () => {
  // BUSINESS: each pair is a text colour and the surface it is drawn on.
  const pairs: [text: string, background: string][] = [
    ["text", "bg"], ["text", "panel"], ["text", "panel-2"],
    ["muted", "bg"], ["muted", "panel"], ["muted", "panel-2"],
    ["accent", "panel"], ["accent-soft", "accent-bg"],
    ["warn-text", "warn-bg"],      // the synthetic-data badge
    ["danger", "panel"],           // delinquent loans
    ["brand-gold", "panel"], ["brand-gold", "brand-navy"],
    ["brand-slate", "panel"], ["brand-slate", "brand-navy"],
  ];

  it.each(pairs)("--%s on --%s", (text, background) => {
    expect(t[text], `--${text} missing from styles.css`).toBeDefined();
    expect(t[background], `--${background} missing from styles.css`).toBeDefined();
    expect(contrastRatio(t[text], t[background])).toBeGreaterThanOrEqual(WCAG_AA_TEXT);
  });

  // BUSINESS: the brand tokens match brand/README.txt ("COLOURS"), the source of truth.
  // TECH: reads the README itself, so the hex values are not copied into this test.
  //   Each README line is "Name  #hex ... [#hex]"; a second hex is the gradient end
  //   (Flask Blue) or the on-white variant (Slate).
  it("mirrors the brand kit's colours in brand/README.txt", () => {
    const readme = readFileSync(resolve(here, "../../../brand/README.txt"), "utf8");
    const lines = readme.split("\n");
    const hexes = (name: string) =>
      [...(lines.find((l) => l.trim().startsWith(name)) ?? "").matchAll(/#[0-9a-f]{6}/gi)]
        .map((m) => m[0].toLowerCase());
    const expected: [token: string, readmeName: string, index: number][] = [
      ["brand-navy", "Lab Navy", 0], ["brand-gold", "Neural Gold", 0], ["brand-amber", "Amber", 0],
      ["brand-flask-blue", "Flask Blue", 0], ["brand-flask-blue-deep", "Flask Blue", 1],
      ["brand-slate", "Slate", 0], ["brand-slate-on-white", "Slate", 1], ["brand-ink-navy", "Ink Navy", 0],
    ];
    for (const [token, name, i] of expected) {
      expect(hexes(name)[i], `${name} in brand/README.txt`).toBeDefined();
      expect(t[token]?.toLowerCase(), `--${token}`).toBe(hexes(name)[i]);
    }
  });
});
