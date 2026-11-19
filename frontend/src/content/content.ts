/**
 * content/content.ts: the SPA's single door to the visitor-facing words in content/.
 *
 * Where it sits: repo content/ (glossary, screen explanations, column terms, desk
 * question labels, screen captions) -> [content.ts] -> Explain panel, glossary
 * tooltips, grid header tooltips, panel captions, desk-question chips.
 *
 * BUSINESS: every term is defined once, in content/glossary.json, and every screen's
 *   explanation lives in content/screens/<screen>.md (.claude/rules/showcase.md).
 *   Components never hard-code these words; they ask this module.
 * TECH: Vite bundles the files at build time. "@content" is an alias for ../content
 *   (vite.config.ts). A JSON import becomes a JavaScript object; "?raw" imports a
 *   Markdown file as one string, split here into its Business and Technical sections
 *   and rendered later by react-markdown.
 */
import deskQuestionsJson from "@content/desk-questions.json";
import glossaryJson from "@content/glossary.json";
import loanColumnsJson from "@content/loan-columns.json";
import loanTapeJson from "@content/screens/loan-tape.json";
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
 * One desk-question chip's words.
 * BUSINESS: "LTV over 125", with the HARP glossary entry as its tooltip.
 * TECH: id matches backend/app/config/desk_questions.toml, where the rule lives; the
 *   back-end tests check the two files list the same ids in the same order.
 */
export interface DeskQuestionLabel {
  id: string;
  label: string;
  term: string;
}

export const deskQuestionLabels: DeskQuestionLabel[] = deskQuestionsJson.questions;

/**
 * Each screen's explanation, Markdown with "## Business" and "## Technical" sections.
 * TECH: keyed by screen id; new screens add their file here.
 */
export const screenExplanations = {
  "loan-tape": loanTapeMd,
} as const;

export type ScreenId = keyof typeof screenExplanations;

/**
 * The glossary terms each screen's Explain panel offers, the first shown open.
 * BUSINESS: the words a visitor needs to read that screen.
 * TECH: from content/screens/<screen>.json "terms"; a unit test checks each exists.
 */
export const screenTerms: Record<ScreenId, string[]> = {
  "loan-tape": loanTapeJson.terms,
};

/** A screen explanation split for the Explain panel's two tabs. */
export interface ExplanationSections {
  business: string;
  technical: string;
}

/**
 * Split a screen's Markdown into its Business and Technical sections.
 * BUSINESS: the Explain panel shows one at a time, as two tabs.
 * TECH: everything after the "## Business" heading up to "## Technical" is Business;
 *   everything after "## Technical" is Technical. The headings themselves are dropped
 *   (the tabs name them). A missing section gives "" (a unit test checks every
 *   screen file has both). The `m` flag makes ^ and $ match at each line.
 */
export function splitExplanation(md: string): ExplanationSections {
  const biz = /^## Business$/m.exec(md);
  const tech = /^## Technical$/m.exec(md);
  const after = (m: RegExpExecArray | null) => (m ? m.index + m[0].length : -1);
  const business = biz ? md.slice(after(biz), tech && tech.index > biz.index ? tech.index : undefined) : "";
  const technical = tech ? md.slice(after(tech), biz && biz.index > tech.index ? biz.index : undefined) : "";
  return { business: business.trim(), technical: technical.trim() };
}

/**
 * The Loan Tape screen's short captions and Explain-panel terms.
 * BUSINESS: panel subtitles and footnotes, in content/ so they can be edited without
 *   touching code. TECH: from content/screens/loan-tape.json.
 */
export const loanTapeContent = loanTapeJson;

/**
 * Fill {name} placeholders in a caption.
 * BUSINESS: "server-paged, {blockSize} loans per block" reads the real block size, so
 *   the caption cannot drift from gridConfig.ts. TECH: unknown names stay as written.
 */
export function fillCaption(text: string, values: Record<string, string | number>): string {
  return text.replace(/\{(\w+)\}/g, (whole, name: string) =>
    name in values ? String(values[name]) : whole,
  );
}
