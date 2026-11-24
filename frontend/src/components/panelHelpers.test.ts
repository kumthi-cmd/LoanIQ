/**
 * Tests for components/barScale.ts and components/rateBuckets.ts.
 * BUSINESS: bars compare sizes honestly (the largest is full length, a tiny one is
 *   still visible, nothing is drawn for zero), and every note-rate bar is labelled the
 *   way a trader says it, including the open ends ("below 2.5%", "9.0%+").
 */
import { describe, expect, it } from "vitest";
import type { RateBucket } from "../api/types";
import { barPercent, barWidth, MIN_BAR_PERCENT } from "./barScale";
import { axisLabels, bucketDescription, bucketLabel, bucketLows, bucketWidth } from "./rateBuckets";

describe("barScale", () => {
  it("scales to the largest value, with a floor for small values", () => {
    expect(barPercent(50, 200)).toBe(25);
    expect(barPercent(200, 200)).toBe(100);
    expect(barPercent(1, 1000)).toBe(MIN_BAR_PERCENT);
    expect(barWidth(8.14, 212.8)).toBe("3.8%");
  });

  it("draws nothing for zero or for an empty tape", () => {
    // BUSINESS: "0 REO loans" must not look like a few.
    expect(barPercent(0, 100)).toBe(0);
    expect(barPercent(5, 0)).toBe(0);
    expect(barWidth(0, 0)).toBe("0.0%");
  });
});

// TECH: 2.0% to 9.0%+ in half points, as api.toml sets it: 15 buckets.
const BUCKETS: RateBucket[] = Array.from({ length: 15 }, (_, i) => ({
  low: i === 0 ? null : 2 + i * 0.5,
  high: i === 14 ? null : 2.5 + i * 0.5,
  loans: i,
  current_upb: i * 1e6,
}));

describe("rateBuckets", () => {
  it("labels closed and open buckets", () => {
    expect(bucketLabel(BUCKETS[0])).toBe("below 2.5%");
    expect(bucketLabel(BUCKETS[8])).toBe("6.0–6.5%");
    expect(bucketLabel(BUCKETS[14])).toBe("9.0%+");
    expect(bucketLabel({ low: null, high: null, loans: 1, current_upb: 1 })).toBe("all rates");
  });

  it("describes a bucket in $M and loans", () => {
    expect(bucketDescription({ low: 6, high: 6.5, loans: 312, current_upb: 114_940_000 }))
      .toBe("6.0–6.5%: $114.9M, 312 loans");
  });

  it("fills in the first bucket's lower edge from the bucket width", () => {
    expect(bucketLows(BUCKETS).slice(0, 3)).toEqual([2, 2.5, 3]);
    expect(bucketLows([{ low: null, high: 2.5, loans: 0, current_upb: 0 }])).toEqual([null]);
  });

  // BUSINESS: the axis reads as on the "1 · Loan Tape" board: 2.0% ... 8.0%, then "9%+"
  //   (Step 1g: the open end is written short; the bar's hover text keeps "9.0%+").
  it("puts axis labels every 2 points and a short label on the open last bucket", () => {
    const labels = axisLabels(BUCKETS);
    expect(labels.filter(Boolean)).toEqual(["2.0%", "4.0%", "6.0%", "8.0%", "9%+"]);
    expect(labels[0]).toBe("2.0%");
    expect(labels).toHaveLength(15);
    expect(bucketLabel(BUCKETS[14])).toBe("9.0%+");
  });

  // TECH: a half-point open end keeps its decimal, so "9.5%+" is never shown as "10%+".
  it("keeps a half point in the open-ended label", () => {
    const open = [{ low: 9, high: 9.5, loans: 1, current_upb: 1 }, { low: 9.5, high: null, loans: 1, current_upb: 1 }];
    expect(axisLabels(open)[1]).toBe("9.5%+");
  });

  // BUSINESS: the panel caption says "UPB by 0.5% bucket", read from the data.
  it("reads the bucket width from the first closed bucket", () => {
    expect(bucketWidth(BUCKETS)).toBe(0.5);
    expect(bucketWidth([{ low: 6, high: 6.25, loans: 0, current_upb: 0 }])).toBe(0.25);
    expect(bucketWidth([{ low: null, high: null, loans: 0, current_upb: 0 }])).toBeNull();
  });
});
