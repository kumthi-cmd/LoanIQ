/**
 * components/SummaryPanel.tsx: the card frame shared by the Loan Tape's three panels.
 *
 * Where it sits: ProgramMixPanel, NoteRatePanel, DelinquencyPanel -> [SummaryPanel].
 *
 * BUSINESS: each panel answers one question about the tape's shape (who can buy it,
 *   what coupons it holds, how much is late), with a title and a unit caption, so a
 *   visitor always knows whether a number is dollars or loans.
 * TECH: a <section> with an accessible name (aria-label), so tests and screen
 *   readers find "Program mix" as a region. While data is loading, children is
 *   replaced by a placeholder line, so the card keeps its place and the page does
 *   not jump when the numbers arrive.
 */
import type { ReactNode } from "react";

interface SummaryPanelProps {
  /** Accessible name of the region, for example "Program mix". */
  name: string;
  /** What the title shows; defaults to the name (may hold a glossary-linked word). */
  title?: ReactNode;
  /** The unit caption at top right, for example "Current UPB, $M". */
  caption: string;
  /** False while the API call is in flight. */
  loaded: boolean;
  children: ReactNode;
}

/**
 * One summary card.
 * BUSINESS: a titled, unit-labelled panel. TECH: "…" while loading.
 */
export function SummaryPanel({ name, title, caption, loaded, children }: SummaryPanelProps) {
  return (
    <section className="summary-panel" aria-label={name}>
      <div className="panel-head">
        <span className="panel-title">{title ?? name}</span>
        <span className="panel-caption">{caption}</span>
      </div>
      {loaded ? children : <span className="muted">…</span>}
    </section>
  );
}
