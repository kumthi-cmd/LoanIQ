/**
 * components/NoteRatePanel.tsx: the note-rate distribution, current UPB per half point.
 *
 * Where it sits: GET /api/loans/breakdowns (note_rates) -> Loan Tape screen -> [NoteRatePanel].
 *
 * BUSINESS: the note rate decides which TBA coupons a loan can be delivered into, so
 *   the desk needs the whole spread of rates, not just the WAC. A tape originated in
 *   2020-2021 and again in 2023-2025 has two clusters (around 3-4.5% and 6-7%) whose
 *   WAC sits between them, at a rate few loans actually have; the two clusters price
 *   into very different coupons. The bars show where the balance really is.
 * TECH: one column per bucket, in rate order, every bucket present (empty ones are a
 *   visible gap). Bar height is the bucket's UPB as a percent of the largest bucket's
 *   (barScale.ts). Each bar has a hover title and a visually hidden text with its
 *   range, $M and loan count, so the chart is readable without seeing it. Axis
 *   labels come from rateBuckets.ts, from the data, never a copy of api.toml.
 */
import type { RateBucket } from "../api/types";
import { loanTapeContent } from "../content/content";
import { barPercent } from "./barScale";
import { GlossaryTerm } from "./GlossaryTerm";
import { axisLabels, bucketDescription, bucketLabel } from "./rateBuckets";
import { SummaryPanel } from "./SummaryPanel";

interface NoteRatePanelProps {
  /** Buckets from the API in rate order; null while loading. */
  buckets: RateBucket[] | null;
}

/**
 * The Note rate distribution panel.
 * BUSINESS: where the tape's balance sits by coupon.
 * TECH: a 0 bar gets no height at all (barPercent floors only values above 0).
 */
export function NoteRatePanel({ buckets }: NoteRatePanelProps) {
  const list = buckets ?? [];
  const max = Math.max(0, ...list.map((b) => b.current_upb));
  const labels = axisLabels(list);
  const { noteRate, noteRateNote } = loanTapeContent.captions;
  return (
    <SummaryPanel name="Note rate distribution" loaded={buckets !== null} caption={noteRate}
      title={<><GlossaryTerm term="Note rate">Note rate</GlossaryTerm> distribution</>}>
      <ul className="histogram">
        {list.map((b) => (
          <li key={bucketLabel(b)} className="histogram-col" title={bucketDescription(b)}>
            <span className="histogram-bar" style={{ height: `${barPercent(b.current_upb, max).toFixed(1)}%` }} />
            <span className="visually-hidden">{bucketDescription(b)}</span>
          </li>
        ))}
      </ul>
      <div className="histogram-axis" aria-hidden="true">
        {labels.map((label, i) => (
          <span key={i}>{label}</span>
        ))}
      </div>
      <span className="panel-note">{noteRateNote}</span>
    </SummaryPanel>
  );
}
