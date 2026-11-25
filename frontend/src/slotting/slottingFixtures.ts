/**
 * slotting/slottingFixtures.ts: sample Product Slotting API answers for the front-end tests.
 *
 * BUSINESS: the seeded tape's real run (backend/tests/test_slotting.py checks these
 *   numbers against the engine): 1,467 of 2,000 slotted, 1,012 UMBS and 455 GNMA II;
 *   312 no agency pool, 85 no TBA product, 136 delinquent; LLB 974, Low FICO 379, NY 72,
 *   PR 17; 363 generic TBA. LN78265415 is the board's hover loan.
 * TECH: test data only; no screen imports it. Shapes are the generated API types, so
 *   a change to the back end's models breaks the type check here, not silently.
 */
import type { LoanSlots, RulesSummary, SlottingStatus } from "../api/types";
import type { StepEvent } from "./slottingStream";

export const RULES: RulesSummary = {
  rules: 12,
  families: [
    { family: "LLB", label: "LLB", tiers: ["85K", "110K", "125K", "150K", "175K", "200K", "225K", "250K", "275K"] },
    { family: "NY", label: "NY", tiers: [] },
    { family: "PR", label: "PR", tiers: [] },
    { family: "LOW_FICO", label: "Low FICO", tiers: [] },
  ],
};

export const NOT_RUN: SlottingStatus = { run: false, running: false, run_at: null, totals: null, rules: RULES };

export const RUN: SlottingStatus = {
  run: true,
  running: false,
  run_at: "2026-11-25T16:42:00Z",
  rules: RULES,
  totals: {
    loans: 2000, slotted: 1467, not_slotted: 533,
    by_agency: { UMBS: 1012, "GNMA II": 455 },
    by_reason: { no_agency: 312, product: 85, status: 136 },
    stories: { LLB: 974, NY: 72, PR: 17, LOW_FICO: 379 },
    tiers: { LLB: { LLB_85K: 55 } },
    with_story: 1104, generic_tba: 363, multi_story: 323,
    coupons: { down_min: "1.5", down_max: "8.0", up_min: "2.0", up_max: "8.5" },
  },
};

/** BUSINESS: three of the run's 13 steps, enough to watch the pacing. */
export const STEPS: StepEvent[] = [
  { step: 1, steps: 3, kind: "load_tape", name: "Loading the tape", percent: 33, line: "Loaded 2,000 loans from the tape" },
  { step: 2, steps: 3, kind: "agency", name: "Checking agency eligibility", percent: 67,
    line: "312 Jumbo and Non-QM loans have no agency pool: not slotted" },
  { step: 3, steps: 3, kind: "write", name: "Writing to the Loan Tape", percent: 100,
    line: "Wrote 1,467 slots to the Loan Tape; 363 loans have no story and go generic TBA" },
];

/** The run's stream body: the steps, then done. */
export function streamText(steps: StepEvent[] = STEPS, done: SlottingStatus = RUN): string {
  return steps.map((s) => `event: step\ndata: ${JSON.stringify(s)}\n\n`).join("")
    + `event: done\ndata: ${JSON.stringify(done)}\n\n`;
}

export const BOARD_CARD: LoanSlots = {
  loan_id: "LN78265415", run_at: RUN.run_at!, slotted: true,
  loan: { seller: "Alder & Finch Mortgage", state: "NY", program: "Conventional", product: "30Y Fixed",
    note_rate: 3.125, orig_upb: 268800, fico: 674, dq_status: "Current" },
  agency: "UMBS", term: "30Y", slot: "UMBS 30Y 2.5 / 3.0", down_coupon: "2.5", up_coupon: "3.0",
  stories: [
    { name: "LLB_275K", label: "LLB 275K", rule: "orig_upb <= 275000",
      why: "Original balance $268,800 fits the $275K tier, the lowest it fits" },
    { name: "NY", label: "NY", rule: "state = 'NY'", why: "Property in New York" },
    { name: "LOW_FICO", label: "Low FICO", rule: "fico < 700", why: "FICO 674, below the Low FICO cut-off in the rule" },
  ],
  generic_tba: "Generic TBA · UMBS 30Y 2.5", generic_note: "always open", not_slotted: null,
};

export const ARM_CARD: LoanSlots = {
  loan_id: "LN79962194", run_at: RUN.run_at!, slotted: false,
  loan: { seller: "Stonemere Mortgage", state: "IN", program: "Conventional", product: "7/6 ARM",
    note_rate: 2.625, orig_upb: 140900, fico: 758, dq_status: "Current" },
  agency: "UMBS", term: null, slot: "Not slotted", stories: [],
  not_slotted: { reason: "product", short: "No TBA product",
    text: "A 7/6 ARM has no fixed-rate TBA coupon. ARM pools are out of scope for now." },
};
