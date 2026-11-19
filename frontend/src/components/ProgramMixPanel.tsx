/**
 * components/ProgramMixPanel.tsx: current UPB by program, as horizontal bars.
 *
 * Where it sits: GET /api/loans/breakdowns (programs) -> Loan Tape screen -> [ProgramMixPanel].
 *
 * BUSINESS: the program decides who can buy a loan: Conventional and High-Balance go
 *   to the GSEs (UMBS), FHA, VA and USDA to Ginnie Mae, Jumbo and Non-QM to banks and
 *   private investors. A tape that is mostly Jumbo is a very different trade from one
 *   that is mostly Conventional, even at the same WAC. Balance, not loan count, is
 *   what the desk sizes trades by, so bars are current UPB in $ millions.
 * TECH: the API sends programs largest first, so the bars read top-down. Each bar's
 *   width is its UPB as a percent of the largest program's UPB (the largest is full
 *   width), with a small floor so a tiny program is still visible (barScale.ts). The bar is
 *   decorative (aria-hidden); the number next to it carries the value. Program
 *   names are glossary terms, so hovering "Non-QM" explains it.
 */
import type { ProgramSlice } from "../api/types";
import { loanTapeContent } from "../content/content";
import { formatMillions, formatNumber } from "../grid/columnFormats";
import { barWidth } from "./barScale";
import { GlossaryTerm } from "./GlossaryTerm";
import { SummaryPanel } from "./SummaryPanel";

interface ProgramMixPanelProps {
  /** Programs from the API, largest UPB first; null while loading. */
  programs: ProgramSlice[] | null;
}

/**
 * The Program mix panel.
 * BUSINESS: how the tape's balance splits across programs. TECH: a <ul> of rows.
 */
export function ProgramMixPanel({ programs }: ProgramMixPanelProps) {
  const max = Math.max(0, ...(programs ?? []).map((p) => p.current_upb));
  return (
    <SummaryPanel name="Program mix" caption={loanTapeContent.captions.programMix} loaded={programs !== null}>
      <ul className="bar-list">
        {(programs ?? []).map((p) => (
          <li key={p.program} className="bar-row bar-row-program"
            title={`${p.program}: ${formatNumber(p.loans, "count")} loans`}>
            <span className="bar-name">
              <GlossaryTerm term={p.program} />
            </span>
            <span className="bar-track" aria-hidden="true">
              <span className="bar-fill" style={{ width: barWidth(p.current_upb, max) }} />
            </span>
            <span className="bar-value">{formatMillions(p.current_upb)}</span>
          </li>
        ))}
      </ul>
    </SummaryPanel>
  );
}
