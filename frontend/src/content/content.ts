/**
 * content/content.ts: the SPA's single door to the visitor-facing words in content/.
 *
 * Where it sits: repo content/ (glossary, screen explanations, column terms, desk
 * question labels, screen captions, the Showcase pages, build facts, the Ask the
 * Tape agent's explainer and diagram, and Product Slotting's words) ->
 * [content.ts] -> Explain panel, glossary tooltips, grid header tooltips, panel
 * captions, desk-question chips, the About and How it was built pages.
 *
 * BUSINESS: every term is defined once, in content/glossary.json, and every screen's
 *   explanation lives in content/screens/<screen>.md (.claude/rules/showcase.md).
 *   Components never hard-code these words; they ask this module.
 * TECH: Vite bundles the files at build time. "@content" is an alias for ../content
 *   (vite.config.ts). A JSON import becomes a JavaScript object; "?raw" imports a
 *   Markdown file as one string, split here into its Business and Technical sections
 *   and rendered later by react-markdown.
 */
import aboutMd from "@content/about.md?raw";
import agentMd from "@content/agent.md?raw";
// TECH: an SVG import without "?raw" gives its URL, not its text: Vite copies the
//   file into the build with a content hash in its name (or inlines a small one as
//   a data: URL). The page shows it with <img src>, so its markup never enters the DOM.
import agentDiagramSvgUrl from "@content/diagrams/ask-the-tape-agent.svg";
import askTheTapeJson from "@content/ask-the-tape.json";
import askTheTapeScreenJson from "@content/screens/ask-the-tape.json";
import askTheTapeMd from "@content/screens/ask-the-tape.md?raw";
import buildFactsJson from "@content/build-facts.json";
import buildLogMd from "@content/build-log.md?raw";
import deskQuestionsJson from "@content/desk-questions.json";
import howItWasBuiltMd from "@content/how-it-was-built.md?raw";
import glossaryJson from "@content/glossary.json";
import loanColumnsJson from "@content/loan-columns.json";
import loanTapeJson from "@content/screens/loan-tape.json";
import loanTapeMd from "@content/screens/loan-tape.md?raw";
import productSlottingJson from "@content/screens/product-slotting.json";
import productSlottingMd from "@content/screens/product-slotting.md?raw";
import slottingJson from "@content/slotting.json";

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
  "ask-the-tape": askTheTapeMd,
  // BUSINESS: Product Slotting is a Loan Tape action, not a screen (Step 5b), but it
  //   explains itself like one; the Loan Tape's Explain panel switches to it.
  "product-slotting": productSlottingMd,
} as const;

export type ScreenId = keyof typeof screenExplanations;

/**
 * The glossary terms each screen's Explain panel offers, the first shown open.
 * BUSINESS: the words a visitor needs to read that screen.
 * TECH: from content/screens/<screen>.json "terms"; a unit test checks each exists.
 */
export const screenTerms: Record<ScreenId, string[]> = {
  "loan-tape": loanTapeJson.terms,
  "ask-the-tape": askTheTapeScreenJson.terms,
  "product-slotting": productSlottingJson.terms,
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
 * The Ask the Tape screen's captions, prompts, tool blurbs and guardrails (Step 4b).
 * BUSINESS: every word the screen shows that the back end does not send.
 * TECH: the "screen" section of content/ask-the-tape.json; the same file's
 *   "offline" and "notices" sections are read by the back end, never here.
 */
export const askTheTapeContent = askTheTapeJson.screen;

// =============================================================================
// Product Slotting (Step 5b)
// =============================================================================

/**
 * Product Slotting's words on screen: the sidebar action, the run dialog, the
 * Slotting panel, the notice, the hover card and the Explain switch.
 * BUSINESS: every word the screen shows that the back end does not send.
 * TECH: the "screen" section of content/slotting.json. The same file's other
 *   sections are the back end's (commentary templates, story labels, reasons); the
 *   screen reads three of them too, so the grid can tell a story list from a
 *   generic or not-slotted cell (slottingCellWords).
 */
export const slottingContent = slottingJson.screen;

/**
 * BUSINESS: the Slot and Spec Stories texts that are not a list of stories.
 * TECH: notSlotted is the Slot text of a loan that is not slotted; generic is the
 *   Spec Stories text of a slotted loan with no story; reasons are the short
 *   not-slotted reasons shown in Spec Stories ("Delinquent").
 */
export const slottingCellWords = {
  notSlotted: slottingJson.slot.not_slotted,
  generic: slottingJson.slot.generic,
  reasons: Object.values(slottingJson.reasons).map((r) => r.short),
  reasonShort: Object.fromEntries(Object.entries(slottingJson.reasons).map(([k, r]) => [k, r.short])) as Record<string, string>,
} as const;

// =============================================================================
// The Agent mark's explainer (Step 4d)
// =============================================================================

/**
 * How the Ask the Tape agent works, as one Markdown file, and the loop diagram.
 * BUSINESS: the Agent mark (sidebar and screen title) opens these, so a visitor can
 *   see what Claude does and what LoanIQ's code does, without leaving the screen.
 * TECH: agentMd is the raw text of content/agent.md, rendered whole by
 *   ShowcaseMarkdown. agentDiagramUrl is the URL of
 *   content/diagrams/ask-the-tape-agent.svg, for an <img>; its alt text is
 *   askTheTapeContent.agentMark.diagramAlt.
 */
export const agentExplainer = {
  markdown: agentMd,
  diagramUrl: agentDiagramSvgUrl,
} as const;

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

// =============================================================================
// Showcase pages: About and How it was built
// =============================================================================

/**
 * The Showcase pages' Markdown, rendered whole by react-markdown.
 * BUSINESS: what LoanIQ is (About), how it was built AI-first, and the build log of
 *   every step, newest first. You edit the words in content/, never in a component.
 * TECH: "?raw" strings, like the screen explanations, but not split into sections.
 */
export const showcasePages = {
  about: aboutMd,
  howItWasBuilt: howItWasBuiltMd,
  buildLog: buildLogMd,
} as const;

/**
 * The "By the numbers" facts, written by test.ps1 after every layer passes.
 * BUSINESS: proof, not claims: how many tests guard LoanIQ, how much of the back end
 *   they cover, and how many commits it took, as of the last full test run.
 * TECH: every field is optional. content/build-facts.json is committed by hand after
 *   a test run, so an older or partly written file must still render (the page shows
 *   a dash for a missing number). Units: coverage in percent (98.8 means 98.8%);
 *   date as YYYY-MM-DD.
 */
export interface BuildFacts {
  backendTests?: number;
  frontendTests?: number;
  e2eTests?: number;
  backendCoverage?: number;
  commits?: number;
  date?: string;
}

/**
 * Keep only well-typed fields from a build-facts object.
 * BUSINESS: a hand-edited or half-written file never shows "NaN" or nonsense.
 * TECH: numbers must be finite and not negative; date must be a string. Anything
 *   else, including a non-object input, is dropped.
 */
export function parseBuildFacts(raw: unknown): BuildFacts {
  const facts: BuildFacts = {};
  if (typeof raw !== "object" || raw === null) return facts;
  const r = raw as Record<string, unknown>;
  const numberKeys = ["backendTests", "frontendTests", "e2eTests", "backendCoverage", "commits"] as const;
  for (const key of numberKeys) {
    const v = r[key];
    if (typeof v === "number" && Number.isFinite(v) && v >= 0) facts[key] = v;
  }
  if (typeof r.date === "string" && r.date) facts.date = r.date;
  return facts;
}

export const buildFacts: BuildFacts = parseBuildFacts(buildFactsJson);
