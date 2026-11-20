/**
 * theme/contrast.ts: WCAG text-contrast arithmetic for the LoanIQ colour tokens.
 *
 * Where it sits: used by theme/contrast.test.ts, which reads the real tokens out of
 *   styles.css and checks every text colour against the background it sits on.
 *
 * BUSINESS: a desk screen is read for hours, often on a second monitor. Text that is
 *   too faint is missed, and that includes the synthetic-data warning. WCAG AA asks
 *   for 4.5:1 for normal text; this file makes that a number the tests can check
 *   whenever someone changes a colour.
 * TECH: the formula is WCAG 2.x "relative luminance" and "contrast ratio":
 *   - each sRGB channel c in 0..1 is linearised: c <= 0.03928 ? c / 12.92
 *     : ((c + 0.055) / 1.055) ^ 2.4
 *   - luminance L = 0.2126 R + 0.7152 G + 0.0722 B (the eye is most sensitive to green)
 *   - ratio = (L_lighter + 0.05) / (L_darker + 0.05), from 1:1 (same) to 21:1 (black/white).
 *   Only 6-digit hex colours (#0b111b) are accepted, which is all styles.css uses.
 */

/** BUSINESS: WCAG AA minimum for normal-size text. */
export const WCAG_AA_TEXT = 4.5;

/**
 * Relative luminance of a colour.
 * BUSINESS: how bright a colour looks to the eye, from 0 (black) to 1 (white).
 * TECH: input "#rrggbb" (case-insensitive); throws on anything else so a typo in a
 *   token fails the test instead of passing silently.
 */
export function luminance(hex: string): number {
  const m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(hex.trim());
  if (!m) throw new Error(`Not a #rrggbb colour: ${hex}`);
  // TECH: undo the sRGB gamma curve so the channels add up linearly.
  const [r, g, b] = m.slice(1).map((h) => {
    const c = parseInt(h, 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/**
 * Contrast ratio between a text colour and its background.
 * BUSINESS: 4.5 or more reads comfortably for normal text (WCAG AA).
 * TECH: symmetric: the order of the two colours does not matter. Returns 1..21.
 */
export function contrastRatio(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/**
 * Read the colour tokens (--name: #rrggbb) from a CSS file's text.
 * BUSINESS: the test checks the colours the page really uses, not a copy of them.
 * TECH: a small regular expression over the text, not a CSS parser; it finds every
 *   "--name: #hex" declaration. Returns a map like { bg: "#0b111b" }.
 */
export function readColorTokens(css: string): Record<string, string> {
  const tokens: Record<string, string> = {};
  for (const m of css.matchAll(/--([a-z0-9-]+):\s*(#[0-9a-f]{6})\b/gi)) tokens[m[1]] = m[2];
  return tokens;
}
