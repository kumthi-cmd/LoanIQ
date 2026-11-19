/**
 * components/ExplainPanel.tsx: the "Explain this screen" panel on every screen.
 *
 * Where it sits: any screen -> [ExplainPanel] -> content/screens/<screen>.md.
 *
 * BUSINESS: a capital markets or technology visitor opens it to read what the desk
 *   uses the screen for (Business) and how it is built (Technical).
 * TECH: the words live in Markdown under content/ (.claude/rules/showcase.md), loaded
 *   by content.ts and rendered by react-markdown, which turns Markdown into React
 *   elements without injecting raw HTML. Closed by default so the grid gets the
 *   space; the button's aria-expanded tells screen readers whether it is open.
 */
import { useState } from "react";
import Markdown from "react-markdown";
import { screenExplanations, type ScreenId } from "../content/content";

interface ExplainPanelProps {
  /** Which screen's explanation to show, for example "loan-tape". */
  screen: ScreenId;
}

/**
 * The explain toggle and panel.
 * BUSINESS: every screen explains itself.
 * TECH: useState is a React hook holding a value that, when changed, redraws the
 *   component; here it is whether the panel is open.
 */
export function ExplainPanel({ screen }: ExplainPanelProps) {
  const [open, setOpen] = useState(false);
  const panelId = `explain-${screen}`;
  return (
    <div className="explain">
      <button
        type="button"
        className="explain-toggle"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((o) => !o)}
      >
        {open ? "Hide explanation" : "Explain this screen"}
      </button>
      {open && (
        <aside id={panelId} className="explain-panel" aria-label="Screen explanation">
          <Markdown>{screenExplanations[screen]}</Markdown>
        </aside>
      )}
    </div>
  );
}
