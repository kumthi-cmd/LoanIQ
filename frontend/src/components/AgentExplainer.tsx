/**
 * components/AgentExplainer.tsx: the popover the Agent mark opens: how the Ask the
 * Tape agent works, in words and in one diagram.
 *
 * Where it sits: AgentMark -> [AgentExplainer] -> content/agent.md (ShowcaseMarkdown)
 * and content/diagrams/ask-the-tape-agent.svg (an <img>), both via content.ts.
 *
 * BUSINESS: a visitor reads, without leaving the screen, that Claude only plans and
 *   explains, LoanIQ's code checks every call, and every number comes from DuckDB.
 *   That is why the desk can trust an answer from Ask the Tape.
 * TECH:
 *   - role="dialog", named by its own heading (aria-labelledby -> the "#" heading of
 *     content/agent.md). Not modal: the page behind stays usable.
 *   - Opens with focus on the dialog itself, so a screen reader announces it and Tab
 *     moves through it. Esc, a click outside it, or Close calls onClose; the mark
 *     then takes focus back.
 *   - "Outside" means outside both the dialog and the mark: a press on the mark
 *     toggles the popover through the mark's own click instead.
 *   - Placed with position: fixed just under the mark, kept inside the window.
 *     Units are CSS pixels. A long text scrolls inside the popover.
 *   - The diagram is an <img>, not inlined SVG, so its markup never enters the page.
 */
import { useEffect, useId, useRef, type RefObject } from "react";
import { agentExplainer, askTheTapeContent } from "../content/content";
import { ShowcaseMarkdown } from "./ShowcaseMarkdown";

const words = askTheTapeContent.agentMark;

/** TECH: the popover's widest size and the gap it keeps from the window edges, in px. */
const MAX_WIDTH = 560;
const EDGE = 16;

interface AgentExplainerProps {
  /** The mark's box on screen when the popover opened; null places it top-left. */
  anchor: DOMRect | null;
  /** The mark that opened it: a press on it is not an "outside click". */
  trigger: RefObject<HTMLElement | null>;
  /** Close the popover; "outside" for a click outside it (the caller then puts focus
   *  back on the mark only if the click did not move it somewhere else). */
  onClose: (how?: "key" | "outside") => void;
}

/**
 * Where the popover goes, in CSS pixels.
 * TECH: under the mark, left-aligned with it, but never past the right edge. If the
 *   mark is low in the window, the popover starts near the top instead, so it has
 *   room. maxHeight lets the rest scroll inside the popover.
 */
export function popoverPlacement(anchor: DOMRect | null, winW: number, winH: number) {
  const width = Math.min(MAX_WIDTH, winW - 2 * EDGE);
  const left = Math.max(EDGE, Math.min(anchor?.left ?? EDGE, winW - width - EDGE));
  let top = (anchor?.bottom ?? EDGE) + 8;
  if (top > winH * 0.6) top = EDGE;
  return { left, top, width, maxHeight: Math.max(160, winH - top - EDGE) };
}

/**
 * The agent explainer popover.
 * BUSINESS: content/agent.md word for word, then the loop diagram.
 */
export function AgentExplainer({ anchor, trigger, onClose }: AgentExplainerProps) {
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();

  // TECH: focus the dialog once, when it opens (useEffect runs after it is drawn).
  useEffect(() => {
    ref.current?.focus();
  }, []);

  // TECH: listen on the whole document while open; the cleanup function returned
  //   from useEffect removes the listeners when the popover closes.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    };
    const onPointer = (e: MouseEvent) => {
      const target = e.target as Node;
      if (ref.current?.contains(target) || trigger.current?.contains(target)) return;
      onClose("outside");
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onPointer);
    };
  }, [onClose, trigger]);

  const place = popoverPlacement(anchor, window.innerWidth, window.innerHeight);

  return (
    <div ref={ref} role="dialog" aria-labelledby={titleId} tabIndex={-1} className="agent-popover"
      style={place}>
      <button type="button" className="btn agent-popover-close" onClick={() => onClose()}>
        {words.close}
      </button>
      <ShowcaseMarkdown markdown={agentExplainer.markdown} titleId={titleId} />
      <img className="agent-diagram" src={agentExplainer.diagramUrl} alt={words.diagramAlt}
        width={720} height={420} />
    </div>
  );
}
