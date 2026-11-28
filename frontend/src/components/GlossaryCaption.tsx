/**
 * components/GlossaryCaption.tsx: a caption from content/ with glossary terms marked
 * inside it (Step 6c).
 *
 * Where it sits: any screen -> [GlossaryCaption] -> GlossaryTerm -> content/glossary.json.
 *
 * BUSINESS: a caption like "Price and drop in 32nds" should explain "drop" and
 *   "32nds" on hover, while its words stay in content/ where they can be edited
 *   (.claude/rules/showcase.md: never hard-code explanations in components).
 * TECH: the content file marks a term as [[Term]] or [[Term|shown words]]:
 *   "Price and [[Drop|drop]] in [[32nds]]" shows "Price and drop in 32nds", with
 *   "drop" linked to the glossary's "Drop" entry. splitGlossaryCaption does the
 *   parsing, so it is tested without React. Text with no markers renders as is.
 */
import { Fragment } from "react";
import { GlossaryTerm } from "./GlossaryTerm";

/** One piece of a caption: plain text, or a glossary term with the words shown. */
export type CaptionPart = { text: string } | { term: string; text: string };

/**
 * Split a caption into text and [[Term|shown]] parts.
 * BUSINESS: "Spec [[Pay-up|pay-ups]] over TBA" -> "Spec ", pay-ups (the Pay-up
 *   entry), " over TBA".
 * TECH: a regular expression with the g flag finds each [[...]] in turn; the text
 *   between matches is kept as plain parts. An unclosed "[[" is left as text.
 */
export function splitGlossaryCaption(caption: string): CaptionPart[] {
  const parts: CaptionPart[] = [];
  const marker = /\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g;
  let last = 0;
  for (const m of caption.matchAll(marker)) {
    if (m.index > last) parts.push({ text: caption.slice(last, m.index) });
    parts.push({ term: m[1], text: m[2] ?? m[1] });
    last = m.index + m[0].length;
  }
  if (last < caption.length) parts.push({ text: caption.slice(last) });
  return parts;
}

/**
 * The caption as plain words, markers removed.
 * BUSINESS: "Spec [[Pay-up|pay-ups]] over TBA" -> "Spec pay-ups over TBA".
 * TECH: for an accessible name (aria-label). Naming a table by a heading that holds
 *   glossary terms would also read out their hidden definitions.
 */
export function captionText(caption: string): string {
  return splitGlossaryCaption(caption).map((p) => p.text).join("");
}

/**
 * A caption with its glossary terms live.
 * BUSINESS: hover or focus a marked word to read its definition.
 */
export function GlossaryCaption({ text }: { text: string }) {
  return (
    <>
      {splitGlossaryCaption(text).map((p, i) => (
        <Fragment key={i}>{"term" in p ? <GlossaryTerm term={p.term}>{p.text}</GlossaryTerm> : p.text}</Fragment>
      ))}
    </>
  );
}
