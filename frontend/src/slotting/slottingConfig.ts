/**
 * slotting/slottingConfig.ts: how fast the run dialog shows Product Slotting's steps.
 *
 * Where it sits: [slottingConfig] -> slotting/pacer.ts and SlottingContext.tsx.
 *
 * BUSINESS: the server slots the whole tape in a fraction of a second and sends every
 *   step at once. The dialog shows one commentary line at a time, so a visitor can
 *   read what each check found. ILLUSTRATIVE display choices, not engine timings
 *   (docs/decisions.md, "The server runs at full speed; the screen paces the
 *   commentary").
 * TECH: times in milliseconds. With 13 steps, stepMs 350 shows the whole run in about
 *   4.6 s, close to the design board's. doneHoldMs is how long the "Loan Tape updated"
 *   summary stays before the dialog closes by itself. A visitor whose system asks for
 *   reduced motion (prefers-reduced-motion) sees every line at once.
 */
export const slottingConfig = {
  stepMs: 350,
  doneHoldMs: 1500,
} as const;
