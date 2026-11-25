/**
 * slotting/slottingText.ts: the few Product Slotting sentences the screen assembles
 * from API data and the words in content/slotting.json.
 *
 * Where it sits: API data + content -> [slottingText] -> sidebar, dialog, panel, notice.
 *
 * BUSINESS: "Last run 11:42 AM"; "12 rules in 4 spec stories: LLB tiers $85K to $275K,
 *   NY, PR, Low FICO"; "312 No agency pool, 85 No TBA product, 136 Delinquent". Every
 *   number is the API's; every word is content's.
 * TECH: pure functions, so they are tested without a screen. Times are shown in the
 *   visitor's own time zone and locale-independent English ("en-US"), like the rest
 *   of the app's numbers.
 */
import type { RulesSummary, SlottingTotals } from "../api/types";
import { fillCaption, slottingCellWords, slottingContent } from "../content/content";
import { formatNumber } from "../grid/columnFormats";

const { dialog } = slottingContent;

/** BUSINESS: a run's time as a desk reads it: "11:42 AM". TECH: ISO UTC in, local time out. */
export function formatRunTime(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

/**
 * BUSINESS: the confirm dialog's Rules line, from the rules in force.
 * TECH: a tiered family (LLB) reads "LLB tiers $85K to $275K"; the others by label.
 */
export function rulesLine(rules: RulesSummary): string {
  const list = rules.families
    .map((f) => (f.tiers.length > 0
      ? fillCaption(dialog.tierRange, { label: f.label, first: f.tiers[0], last: f.tiers[f.tiers.length - 1] })
      : f.label))
    .join(", ");
  return fillCaption(dialog.rulesValue, {
    rules: formatNumber(rules.rules, "count"), stories: formatNumber(rules.families.length, "count"), list,
  });
}

/**
 * BUSINESS: the not-slotted loans by reason, in the order the checks run.
 * TECH: reason codes come from the totals; their short words from content.
 */
export function reasonsLine(totals: SlottingTotals): string {
  return Object.entries(totals.by_reason)
    .filter(([, n]) => n > 0)
    .map(([code, n]) => fillCaption(dialog.reasonItem, {
      count: formatNumber(n, "count"), short: slottingCellWords.reasonShort[code] ?? code,
    }))
    .join(", ");
}

/** BUSINESS: "1,467 of 2,000 loans slotted: 1,104 with a spec story, 363 generic TBA." */
export function doneSummary(totals: SlottingTotals): string {
  return fillCaption(dialog.doneSummary, {
    slotted: formatNumber(totals.slotted, "count"), loans: formatNumber(totals.loans, "count"),
    withStory: formatNumber(totals.with_story, "count"), generic: formatNumber(totals.generic_tba, "count"),
  });
}

/** BUSINESS: "533 not slotted: 312 No agency pool, ... Hover over a loan ID ..." */
export function doneNotSlotted(totals: SlottingTotals): string {
  return fillCaption(dialog.doneNotSlotted, {
    notSlotted: formatNumber(totals.not_slotted, "count"), reasons: reasonsLine(totals),
  });
}
