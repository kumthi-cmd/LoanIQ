/**
 * grid/SpecStoriesCell.tsx: the Spec Stories cell, one pill per story.
 *
 * Where it sits: GET /api/loans (spec_stories) -> buildColumnDefs -> [SpecStoriesCell].
 *
 * BUSINESS: the stories a loan carries, as on the board: "LLB 275K", "NY", "Low FICO"
 *   each as a pill. "Generic TBA" (slotted, no story) and the not-slotted reasons
 *   ("Delinquent", "No agency pool") show as quiet grey text, because they are not
 *   stories a pay-up can be earned on.
 * TECH: the server sends one text value ("LLB 275K, NY, Low FICO") so the grid can sort
 *   and filter it; the cell splits it on ", " to draw. Which texts are not story lists
 *   comes from content/slotting.json (slottingCellWords), the same words the server
 *   writes, so the two can never disagree.
 */
import type { CustomCellRendererProps } from "ag-grid-react";
import type { LoanRow } from "../api/types";
import { slottingCellWords } from "../content/content";

/** BUSINESS: is this Spec Stories text a list of stories (not generic, not a reason)? */
export function isStoryList(value: string): boolean {
  return value !== "" && value !== slottingCellWords.generic && !slottingCellWords.reasons.includes(value);
}

/** The Spec Stories cell. */
export function SpecStoriesCell(props: CustomCellRendererProps<LoanRow, string | null>) {
  const value = props.value ?? "";
  if (!isStoryList(value)) return <span className="muted">{value}</span>;
  return (
    <span className="story-pills">
      {value.split(", ").map((story) => (
        <span key={story} className="story-pill">{story}</span>
      ))}
    </span>
  );
}
