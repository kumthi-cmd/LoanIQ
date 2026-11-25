/**
 * components/SlottingNavButton.tsx: the sidebar's "5 Product Slotting" action.
 *
 * Where it sits: nav.ts (action: "product-slotting") -> Sidebar -> [SlottingNavButton]
 * -> SlottingContext.open() -> SlottingDialog.
 *
 * BUSINESS: slotting is something the desk does to the Loan Tape, not a screen it
 *   visits (docs/decisions.md), so the sidebar entry is a button, not a link. Under
 *   its name it says whether the tape has been slotted: "Not run on this tape",
 *   "Last run 11:42 AM" or "Running…".
 * TECH: a real <button> with aria-haspopup="dialog", so a screen reader says it opens
 *   a dialog. It works from any screen; the run ends on the Loan Tape.
 */
import { fillCaption, slottingContent } from "../content/content";
import { useSlotting } from "../slotting/SlottingContext";
import { formatRunTime } from "../slotting/slottingText";

const words = slottingContent.nav;

/** The sidebar action. TECH: step is the roadmap step shown in the number column. */
export function SlottingNavButton({ step }: { step: number | null }) {
  const { status, run, open } = useSlotting();
  const busy = run.stage === "running" || run.stage === "done";
  let sub = "";
  if (busy || status?.running) sub = words.running;
  else if (status?.run) sub = fillCaption(words.lastRun, { time: formatRunTime(status.run_at) });
  else if (status) sub = words.notRun;
  return (
    <button type="button" className="nav-link nav-action" aria-haspopup="dialog"
      aria-expanded={run.stage !== "closed"} onClick={open}>
      <span className="nav-step-no" aria-hidden="true">{step ?? ""}</span>
      <span className="nav-action-text">
        <span>{words.label}</span>
        {sub && <span className="nav-action-sub">{sub}</span>}
      </span>
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
        strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="nav-action-icon">
        <path d="M8 5l11 7-11 7z" />
      </svg>
    </button>
  );
}
