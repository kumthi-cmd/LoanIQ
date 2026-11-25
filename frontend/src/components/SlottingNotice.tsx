/**
 * components/SlottingNotice.tsx: "Loan Tape updated by Product Slotting", shown on the
 * Loan Tape right after a run.
 *
 * Where it sits: SlottingContext (notice) -> Loan Tape screen -> [SlottingNotice].
 *
 * BUSINESS: tells the visitor what just changed: how many loans were slotted, and that
 *   hovering a loan ID now explains where it can go. It stays until closed.
 * TECH: role="status" (a polite live region), so a screen reader reads it once
 *   without interrupting. Green is used here for meaning: the run succeeded.
 */
import type { SlottingStatus } from "../api/types";
import { fillCaption, slottingContent } from "../content/content";
import { formatNumber } from "../grid/columnFormats";
import { formatRunTime } from "../slotting/slottingText";

const words = slottingContent.toast;

interface SlottingNoticeProps {
  /** The run just finished. */
  run: SlottingStatus;
  onClose: () => void;
}

/** The notice. */
export function SlottingNotice({ run, onClose }: SlottingNoticeProps) {
  const totals = run.totals;
  return (
    <div role="status" className="slotting-notice">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4"
        strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M5 12.5l4.5 4.5L19 7.5" />
      </svg>
      <strong>{words.title}</strong>
      {totals && (
        <span>
          {fillCaption(words.text, {
            slotted: formatNumber(totals.slotted, "count"), loans: formatNumber(totals.loans, "count"),
          })}
        </span>
      )}
      <span className="slotting-notice-time">{formatRunTime(run.run_at)}</span>
      <button type="button" className="icon-btn" aria-label={words.close} onClick={onClose}>
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
          strokeLinecap="round" aria-hidden="true">
          <path d="M6 6l12 12M18 6L6 18" />
        </svg>
      </button>
    </div>
  );
}
