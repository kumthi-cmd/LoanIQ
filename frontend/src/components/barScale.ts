/**
 * components/barScale.ts: how long a bar is, for the Loan Tape's summary panels.
 *
 * Where it sits: ProgramMixPanel, NoteRatePanel, DelinquencyPanel -> [barScale].
 *
 * BUSINESS: bars compare sizes at a glance (Conventional vs Jumbo balance, 30-day vs
 *   60-day late loans). Every bar in a panel is scaled to the largest one in that
 *   panel, so the biggest is always full length.
 * TECH: plain functions, no React, so they are unit-tested on their own.
 */

// TECH: smallest bar size in percent, so a program or status with a little balance
//   or a few loans still shows.
export const MIN_BAR_PERCENT = 2;

/**
 * A bar's size as a percent of the largest value: (value / max) x 100.
 * BUSINESS: $8.1M of USDA next to $212.8M of Conventional is a short but visible bar.
 * TECH: floored at `floor` for any value above 0; 0 for a zero value or when max is
 *   0 (an empty tape), so nothing is drawn for nothing.
 */
export function barPercent(value: number, max: number, floor = MIN_BAR_PERCENT): number {
  if (max <= 0 || value <= 0) return 0;
  return Math.max(floor, (value / max) * 100);
}

/** The same as a CSS width, one decimal: "37.5%". */
export function barWidth(value: number, max: number, floor = MIN_BAR_PERCENT): string {
  return `${barPercent(value, max, floor).toFixed(1)}%`;
}
