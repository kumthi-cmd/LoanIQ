/**
 * components/GlossaryTerm.tsx: a word with its glossary definition on hover or focus.
 *
 * Where it sits: any screen -> [GlossaryTerm] -> content/glossary.json (via content.ts).
 *
 * BUSINESS: a visitor new to mortgages can hover "WAC" and read what it is and why
 *   the desk cares, without leaving the screen. One definition, shared everywhere.
 * TECH: the definition goes in the browser's native title tooltip and in a hidden
 *   span linked by aria-describedby, so it works with a mouse, a keyboard
 *   (tabIndex=0 makes the word focusable) and a screen reader. An unknown term renders the text without a tooltip; a unit
 *   test checks every term the SPA uses exists.
 */
import { useId, type ReactNode } from "react";
import { termTooltip } from "../content/content";

interface GlossaryTermProps {
  /** The exact glossary term, for example "WAC". */
  term: string;
  /** What to show; defaults to the term itself. */
  children?: ReactNode;
}

/**
 * A glossary-linked word.
 * BUSINESS: explains a term in place.
 * TECH: useId (a React hook) gives a unique id per instance, linking the word to
 *   its hidden description.
 */
export function GlossaryTerm({ term, children }: GlossaryTermProps) {
  const id = useId();
  const tip = termTooltip(term);
  if (!tip) return <>{children ?? term}</>;
  return (
    <span className="glossary-term" title={tip} tabIndex={0} aria-describedby={id}>
      {children ?? term}
      <span id={id} className="visually-hidden">
        {tip}
      </span>
    </span>
  );
}
