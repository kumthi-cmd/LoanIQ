/**
 * components/SlotCard.tsx: the hover card that says where one loan can go.
 *
 * Where it sits: LoanIdCell / LoanGrid (hover or focus on a loan ID) -> Loan Tape screen
 * -> [SlotCard] -> GET /api/loans/{loan_id}/slots.
 *
 * BUSINESS: the board's card. For a slotted loan: its pool and coupons ("UMBS 30Y",
 *   down 2.5, up 3.0), every spec story it fits with the rule and why, the generic TBA
 *   slot that is always open, and a reminder that a loan goes into one pool, so
 *   pay-ups don't stack. For a loan that is not slotted: the reason, in plain English.
 *   The loan's note rate, original balance, FICO and DQ status head the card.
 * TECH:
 *   - Cards are cached per run (run time + loan ID), so hovering the same loan again
 *     is instant and never asks the server twice; a new run starts a fresh cache.
 *   - role="tooltip": the card describes the loan ID; it holds no controls, so the
 *     mouse can leave it closed. Placed with position: fixed beside the hovered cell,
 *     kept inside the window. Units are CSS pixels.
 *   - The useEffect's cleanup ignores a late answer after the visitor has moved on.
 */
import { useEffect, useState } from "react";
import { fetchLoanSlots } from "../api/client";
import type { LoanSlots } from "../api/types";
import { fillCaption, slottingContent } from "../content/content";
import { formatNumber } from "../grid/columnFormats";

const words = slottingContent.card;
// TECH: the card's width and the gap it keeps from the cell and the window edges, in px.
const WIDTH = 380;
const GAP = 8;

// TECH: run time + loan ID -> card, for the life of the page.
const cache = new Map<string, LoanSlots>();

interface SlotCardProps {
  loanId: string;
  /** The hovered cell's box on screen. */
  anchor: DOMRect;
  /** The run the card belongs to (status.run_at), part of the cache key. */
  runAt: string;
}

/**
 * Where the card goes, in CSS pixels.
 * TECH: right of the cell if it fits, else left of it; top aligned with the cell but
 *   moved up if it would run past the bottom (the card is about 420 px tall at most).
 */
export function cardPlacement(anchor: DOMRect, winW: number, winH: number) {
  const right = anchor.right + GAP;
  const left = right + WIDTH <= winW - GAP ? right : Math.max(GAP, anchor.left - WIDTH - GAP);
  const top = Math.max(GAP, Math.min(anchor.top, winH - 420 - GAP));
  return { left, top, width: WIDTH };
}

/** "1 spec story", "3 spec stories", "no spec story". */
function fitsLabel(n: number): string {
  if (n === 0) return words.noStory;
  return n === 1 ? words.oneStory : fillCaption(words.manyStories, { n });
}

/**
 * The slot card.
 * BUSINESS: where this loan can go, or why it cannot.
 */
export function SlotCard({ loanId, anchor, runAt }: SlotCardProps) {
  const key = `${runAt}|${loanId}`;
  const [card, setCard] = useState<LoanSlots | null>(cache.get(key) ?? null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const cached = cache.get(key);
    setError(null);
    if (cached) {
      setCard(cached);
      return;
    }
    setCard(null);
    const ctrl = new AbortController();
    fetchLoanSlots(loanId, ctrl.signal)
      .then((c) => {
        cache.set(key, c);
        setCard(c);
      })
      .catch((e: Error) => {
        if (!ctrl.signal.aborted) setError(e.message);
      });
    return () => ctrl.abort();
  }, [key, loanId]);

  const place = cardPlacement(anchor, window.innerWidth, window.innerHeight);
  return (
    <div id="slot-card" role="tooltip" className="slot-card" style={place}>
      {!card && !error && <span className="muted">{words.loading}</span>}
      {error && <span role="alert">{fillCaption(words.failed, { error })}</span>}
      {card && <CardBody card={card} />}
    </div>
  );
}

/** The card's content once loaded. TECH: money with commas; rates as sent. */
function CardBody({ card }: { card: LoanSlots }) {
  const loan = card.loan as Record<string, string | number | null>;
  const facts: [string, string][] = [
    [words.note, `${formatNumber(loan.note_rate, "rate")}%`],
    [words.orig, `$${formatNumber(loan.orig_upb, "money")}`],
    [words.fico, String(loan.fico ?? "")],
    [words.dq, String(loan.dq_status ?? "")],
  ];
  return (
    <>
      <div className="slot-card-head">
        <span className="mono slot-card-id">{card.loan_id}</span>
        <span className={card.slotted ? "slot-pill slot-pill-yes" : "slot-pill slot-pill-no"}>
          {card.slotted ? words.slotted : words.notSlotted}
        </span>
      </div>
      <span className="muted small">
        {[loan.seller, loan.state, `${loan.program} ${loan.product}`].join(" · ")}
      </span>
      <dl className="slot-facts">
        {facts.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      {card.slotted ? <SlottedPart card={card} /> : (
        <div className="slot-why-not">
          <strong>{words.notSlotted}</strong>
          <span>{card.not_slotted?.text}</span>
        </div>
      )}
    </>
  );
}

/** BUSINESS: the coupons, each story with its rule and why, and generic TBA. */
function SlottedPart({ card }: { card: LoanSlots }) {
  return (
    <>
      <div className="slot-coupons">
        <span className="eyebrow">{words.coupons}</span>
        <strong>{card.agency} {card.term}</strong>
        <span className="slot-coupons-values">
          {words.down} <strong>{card.down_coupon}</strong> · {words.up} <strong>{card.up_coupon}</strong>
        </span>
      </div>
      <span className="eyebrow">{fillCaption(words.whereItCanGo, { fits: fitsLabel(card.stories.length) })}</span>
      <ul className="slot-stories">
        {card.stories.map((s) => (
          <li key={s.name} className="slot-story">
            <span className="slot-story-name">{fillCaption(words.storyName, { label: s.label })}</span>
            <code className="mono">{s.rule}</code>
            <span className="slot-story-why">{s.why}</span>
          </li>
        ))}
        <li className="slot-story slot-story-generic">
          <span className="slot-story-name">{card.generic_tba}</span>
          <span className="muted small">{card.generic_note}</span>
        </li>
      </ul>
      <span className="muted small">{words.footnote}</span>
    </>
  );
}
