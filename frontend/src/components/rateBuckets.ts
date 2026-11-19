/**
 * components/rateBuckets.ts: labels and axis ticks for the note-rate histogram.
 *
 * Where it sits: GET /api/loans/breakdowns (note_rates) -> NoteRatePanel -> [rateBuckets].
 *
 * BUSINESS: a desk reads coupons in half points. Each bar is labelled the way a
 *   trader says it ("6.0–6.5%"), and the two open ends say what they hold: the first
 *   bar also takes any lower rate ("below 2.5%"), the last any higher one ("9.0%+").
 * TECH: the API sends every bucket in rate order with low/high in percent and null
 *   on the open ends (backend/app/tape_panels.py). The bucket width and edges come
 *   from the data, never from a copy of api.toml, so changing the config needs no
 *   front-end change. Plain functions, unit-tested on their own.
 */
import type { RateBucket } from "../api/types";
import { formatMillions, formatNumber } from "../grid/columnFormats";

// BUSINESS: an axis label every 2 percentage points (2.0%, 4.0%, 6.0% ...), so the
//   axis stays readable at 15 bars. TECH: a display choice only.
export const AXIS_TICK_EVERY = 2;

const pct = (n: number) => `${n.toFixed(1)}%`;

/**
 * The text for one bucket.
 * BUSINESS: "6.0–6.5%", "below 2.5%", "9.0%+". TECH: "all rates" if both ends are open
 *   (a config with a single bucket).
 */
export function bucketLabel(b: RateBucket): string {
  if (b.low === null && b.high === null) return "all rates";
  if (b.low === null) return `below ${pct(b.high!)}`;
  if (b.high === null) return `${pct(b.low)}+`;
  return `${b.low.toFixed(1)}–${pct(b.high)}`;
}

/**
 * One bucket in words, for the bar's hover title and for screen readers.
 * BUSINESS: "6.0–6.5%: $114.9M, 312 loans".
 */
export function bucketDescription(b: RateBucket): string {
  return `${bucketLabel(b)}: $${formatMillions(b.current_upb)}M, ${formatNumber(b.loans, "count")} loans`;
}

/**
 * The lower edge of each bucket, filling in the open first one from the bucket width.
 * BUSINESS: the first bar of 2.0-9.0+ in half points starts at 2.0%.
 * TECH: width = high - low of the first closed bucket; the first bucket's edge is its
 *   high minus that width. Returns null for a bucket whose edge cannot be known.
 */
export function bucketLows(buckets: RateBucket[]): (number | null)[] {
  const closed = buckets.find((b) => b.low !== null && b.high !== null);
  const width = closed ? closed.high! - closed.low! : null;
  return buckets.map((b) => {
    if (b.low !== null) return b.low;
    return b.high !== null && width !== null ? Math.round((b.high - width) * 1e6) / 1e6 : null;
  });
}

/**
 * The axis label under each bar, or "" for none.
 * BUSINESS: "2.0%", "4.0%", "6.0%", "8.0%" and "9.0%+" under the right bars.
 * TECH: a bar gets a label if its lower edge is a whole multiple of AXIS_TICK_EVERY
 *   (to within rounding), and the last, open-ended bar always gets its "N%+" label.
 */
export function axisLabels(buckets: RateBucket[]): string[] {
  const lows = bucketLows(buckets);
  return buckets.map((b, i) => {
    if (b.high === null && b.low !== null) return pct(b.low) + "+";
    const low = lows[i];
    if (low === null) return "";
    const ratio = low / AXIS_TICK_EVERY;
    return Math.abs(ratio - Math.round(ratio)) < 1e-9 ? pct(low) : "";
  });
}
