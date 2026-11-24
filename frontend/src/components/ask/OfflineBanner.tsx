/**
 * components/ask/OfflineBanner.tsx: a small banner when built-in rules are answering.
 *
 * Where it sits: AskTheTapeScreen -> [OfflineBanner]; status from GET /api/ask/status.
 *
 * BUSINESS: when the server has no AI key, or today's AI budget or the visitor's
 *   daily questions are used up, LoanIQ's built-in rules ("Offline") answer
 *   instead. The banner says so before the visitor asks, in the server's own words,
 *   and that desk questions and saved queries still work.
 * TECH: shown only for the three reasons that last (unavailable, daily_budget,
 *   visitor_limit). A one-off failure (a timeout) is not a lasting state, so it is
 *   shown as a notice under that one answer instead. role="status" lets a screen
 *   reader announce it politely.
 */
import type { AskStatus } from "../../api/types";
import { askTheTapeContent as words } from "../../content/content";

/** BUSINESS: the fallback reasons that mean "Offline is answering for now". */
export const OFFLINE_REASONS = ["unavailable", "daily_budget", "visitor_limit"];

/** True when the banner should show for this status. */
export function isOffline(status: AskStatus | null): boolean {
  return status?.mode === "offline" && OFFLINE_REASONS.includes(status.reason ?? "");
}

/** The banner, or nothing. */
export function OfflineBanner({ status }: { status: AskStatus | null }) {
  if (!isOffline(status)) return null;
  return (
    <div className="offline-banner" role="status">
      <strong>{words.offlineTitle}</strong>
      <span>{status?.notice}</span>
      <span className="muted">{words.offlineMore}</span>
    </div>
  );
}
