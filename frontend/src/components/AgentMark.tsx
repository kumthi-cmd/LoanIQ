/**
 * components/AgentMark.tsx: the small gold "Agent" mark beside a screen answered by
 * an AI agent, with a tooltip and a popover that explains the agent.
 *
 * Where it sits: Sidebar (after the Ask the Tape link) and AskTheTapeScreen (beside
 * its title) -> [AgentMark] -> AgentExplainer (popover) -> content/agent.md and
 * content/diagrams/ask-the-tape-agent.svg, via content.ts.
 *
 * BUSINESS: a visitor sees at a glance which screen uses Claude. Hovering says what an
 *   agent is in one line (glossary "Agent"); clicking shows how the loop works and who
 *   does what, so it is clear the numbers come from LoanIQ's tools, not from the model.
 * TECH:
 *   - It is a <button>, never placed inside a link: a button inside a link is invalid
 *     HTML, and a click would also navigate. In the sidebar it is the link's sibling.
 *   - The look: the LoanIQ Labs flask (/icon/favicon.svg, published from brand/icon/ by
 *     the brandIcons Vite plugin) at 9 px, a 1 px gap, then "Agent" at 10 px semibold
 *     in Neural Gold, raised like a superscript (styles.css, .agent-mark).
 *   - The tooltip and the popover are drawn in a portal (createPortal) at the end of
 *     <body>, with position: fixed next to the mark. The sidebar scrolls (overflow:
 *     auto), which would otherwise clip anything that sticks out of it.
 *   - The tooltip is for sighted mouse and keyboard users; screen readers get the same
 *     words from a hidden span linked by aria-describedby, as in GlossaryTerm.
 */
import { useCallback, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { askTheTapeContent, lookupTerm } from "../content/content";
import { AgentExplainer } from "./AgentExplainer";

const words = askTheTapeContent.agentMark;

/** TECH: the glossary term the tooltip reads; a unit test checks it exists. */
export const AGENT_TERM = "Agent";

/**
 * The Agent mark.
 * BUSINESS: says "an AI agent answers here", and opens the explanation of that agent.
 * TECH: state is the popover (open or not) and the tooltip (shown or not), plus the
 *   mark's on-screen box (DOMRect, in CSS pixels) to place them by. Enter and Space
 *   click a button natively, so the keyboard needs no extra handler. Closing the
 *   popover (Esc, outside click, Close) puts focus back on this mark.
 */
export function AgentMark() {
  const [open, setOpen] = useState(false);
  const [tip, setTip] = useState(false);
  const [anchor, setAnchor] = useState<DOMRect | null>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const descId = useId();
  const definition = lookupTerm(AGENT_TERM)?.definition ?? "";

  // TECH: read the mark's position at the moment it is needed; the page may have
  //   scrolled or resized since the last time.
  const measure = () => setAnchor(buttonRef.current?.getBoundingClientRect() ?? null);

  const showTip = () => {
    measure();
    setTip(true);
  };

  const toggle = () => {
    measure();
    setTip(false);
    setOpen((o) => !o);
  };

  // BUSINESS: keyboard users land back where they were, on the mark.
  // TECH: useCallback keeps the same function between redraws, so the popover's
  //   document listeners (which depend on it) are not removed and re-added each time.
  //   After Esc or Close, focus goes straight back to the mark. After a click
  //   outside, the browser moves focus itself once the press is handled (to the
  //   clicked box, or to <body> for plain text), so wait for that (setTimeout 0)
  //   and take focus back only if it landed nowhere useful, never stealing it from
  //   a box the visitor just clicked into.
  const close = useCallback((how: "key" | "outside" = "key") => {
    setOpen(false);
    if (how === "key") {
      buttonRef.current?.focus();
      return;
    }
    window.setTimeout(() => {
      const active = document.activeElement;
      if (!active || active === document.body) buttonRef.current?.focus();
    }, 0);
  }, []);

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        className="agent-mark"
        aria-label={words.openLabel}
        aria-describedby={descId}
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={toggle}
        onMouseEnter={showTip}
        onMouseLeave={() => setTip(false)}
        onFocus={showTip}
        onBlur={() => setTip(false)}
      >
        <img src="/icon/favicon.svg" alt="" aria-hidden="true" width={9} height={9} />
        <span>{words.label}</span>
        <span id={descId} className="visually-hidden">{definition}</span>
      </button>
      {/* TECH: the visible tooltip is aria-hidden: the hidden span above already
          gives screen readers the same words. Hidden while the popover is open. */}
      {tip && !open && anchor && definition &&
        createPortal(
          <div className="agent-tip" aria-hidden="true" data-testid="agent-tooltip"
            style={{ left: Math.max(8, anchor.left), top: anchor.bottom + 6 }}>
            {definition}
          </div>,
          document.body,
        )}
      {open &&
        createPortal(<AgentExplainer anchor={anchor} trigger={buttonRef} onClose={close} />, document.body)}
    </>
  );
}
