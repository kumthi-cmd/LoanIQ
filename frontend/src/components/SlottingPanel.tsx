/**
 * components/SlottingPanel.tsx: the Loan Tape's Slotting panel: loans per spec story,
 * generic TBA and not slotted, after a Product Slotting run.
 *
 * Where it sits: GET /api/slotting/status (totals) -> SlottingContext -> Loan Tape
 * screen -> [SlottingPanel]. It takes the middle place of the three panels, where the
 * note-rate distribution was before Step 5b (docs/decisions.md).
 *
 * BUSINESS: how much of the tape can earn a pay-up, and on which story: low loan
 *   balance tiers, Low FICO, New York, Puerto Rico; how much goes generic TBA; and how
 *   much no agency pool takes. A loan can fit several stories, so the story bars add
 *   up to more than the slotted loans; it still goes into one pool. Before any run the
 *   panel says so and offers to run it.
 * TECH: bars scale to the largest count (barScale.ts), loans not dollars, in story
 *   order from spec_stories.toml (the server's order), with each family's label from
 *   the rules summary. Story bars use the accent colour; generic TBA and not slotted
 *   are grey, because they are not stories.
 */
import type { SlottingStatus } from "../api/types";
import { fillCaption, slottingCellWords, slottingContent } from "../content/content";
import { formatNumber } from "../grid/columnFormats";
import { barWidth } from "./barScale";
import { SummaryPanel } from "./SummaryPanel";

const words = slottingContent.panel;

interface SlottingPanelProps {
  /** The last run and the rules; null while loading. */
  status: SlottingStatus | null;
  /** Open the run dialog. */
  onRun: () => void;
}

interface Row {
  name: string;
  loans: number;
  story: boolean;
}

/**
 * The panel's rows from a finished run.
 * BUSINESS: "LLB tiers 974", "Low FICO 379", ..., "Generic TBA 363", "Not slotted 533".
 * TECH: story rows sorted by loans, largest first, as on the board.
 */
export function slottingRows(status: SlottingStatus): Row[] {
  const totals = status.totals;
  if (!totals) return [];
  const families = status.rules?.families ?? [];
  const stories = families
    .map((f) => ({
      name: f.tiers.length > 0 ? fillCaption(words.tiered, { label: f.label }) : f.label,
      loans: totals.stories[f.family] ?? 0,
      story: true,
    }))
    .sort((a, b) => b.loans - a.loans);
  return [
    ...stories,
    { name: slottingCellWords.generic, loans: totals.generic_tba, story: false },
    { name: slottingCellWords.notSlotted, loans: totals.not_slotted, story: false },
  ];
}

/**
 * The Slotting panel.
 * BUSINESS: the tape's spec-story mix, or a way to run slotting.
 */
export function SlottingPanel({ status, onRun }: SlottingPanelProps) {
  const rows = status ? slottingRows(status) : [];
  const max = Math.max(0, ...rows.map((r) => r.loans));
  return (
    <SummaryPanel name={words.name} caption={words.caption} loaded={status !== null}>
      {status?.run ? (
        <>
          <ul className="bar-list">
            {rows.map((r) => (
              <li key={r.name} className="bar-row">
                <span className="bar-name">{r.name}</span>
                <span className="bar-track" aria-hidden="true">
                  <span className={r.story ? "bar-fill" : "bar-fill bar-fill-muted"}
                    style={{ width: barWidth(r.loans, max) }} />
                </span>
                <span className="bar-value">{formatNumber(r.loans, "count")}</span>
              </li>
            ))}
          </ul>
          <span className="panel-note">{words.note}</span>
        </>
      ) : (
        <div className="slotting-not-run">
          <span className="muted">{words.notRun}</span>
          <button type="button" className="btn btn-accent" onClick={onRun}>{words.run}</button>
        </div>
      )}
    </SummaryPanel>
  );
}
