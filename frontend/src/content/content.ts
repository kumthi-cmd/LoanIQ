/**
 * content/content.ts: the SPA's single door to the visitor-facing words in content/.
 *
 * Where it sits: repo content/ (glossary, screen explanations, column terms)
 * -> [content.ts] -> Explain panel, glossary tooltips, grid header tooltips.
 *
 * BUSINESS: every term is defined once, in content/glossary.json, and every screen's
 *   explanation lives in content/screens/<screen>.md (.claude/rules/showcase.md).
 *   Components never hard-code these words; they ask this module.
 * TECH: Vite bundles the files at build time. "@content" is an alias for ../content
 *   (vite.config.ts). A JSON import becomes a JavaScript object; "?raw" imports a
 *   Markdown file as one string, rendered later by react-markdown.
 */
import glossaryJson from "@content/glossary.json";
import loanColumnsJson from "@content/loan-columns.json";
import loanTapeMd from "@content/screens/loan-tape.md?raw";

/** One glossary entry. BUSINESS: the term, what it means and why the desk cares. */
export interface GlossaryEntry {
  term: string;
  definition: string;
  why: string;
}

export const glossary: GlossaryEntry[] = glossaryJson;

// TECH: an index by term for O(1) lookups from tooltips.
const byTerm = new Map(glossary.map((g) => [g.term, g]));

/**
 * Find a glossary entry by its exact term.
 * BUSINESS: one definition per term, shared by every screen.
 * TECH: undefined when the term is missing; a unit test checks every term the
 *   SPA refers to exists, so that only happens if someone renames a term.
 */
export function lookupTerm(term: string): GlossaryEntry | undefined {
  return byTerm.get(term);
}

/** Tooltip text for a term: "definition Why it matters: why". */
export function termTooltip(term: string): string | undefined {
  const g = lookupTerm(term);
  return g ? `${g.definition} Why it matters: ${g.why}` : undefined;
}

/**
 * Column name -> glossary term, for grid header tooltips.
 * BUSINESS: hovering "LTV (%)" explains LTV. TECH: from content/loan-columns.json "terms".
 */
export const columnTerms: Record<string, string> = loanColumnsJson.terms;

/**
 * Each screen's explanation, Markdown with "## Business" and "## Technical" sections.
 * TECH: keyed by screen id; new screens add their file here.
 */
export const screenExplanations = {
  "loan-tape": loanTapeMd,
} as const;

export type ScreenId = keyof typeof screenExplanations;
