/**
 * components/ExplainPanel.tsx: the "Explain this screen" side panel on every screen.
 *
 * Where it sits: any screen -> [ExplainPanel] -> content/screens/<screen>.md (text)
 * and content/screens/<screen>.json (terms) -> content/glossary.json (definitions).
 *
 * BUSINESS: a capital markets or technology visitor reads what the desk uses the
 *   screen for (Business tab) and how it is built (Technical tab), then the terms the
 *   screen depends on: one glossary card, with chips to switch between terms.
 * TECH:
 *   - The words live in Markdown and JSON under content/ (.claude/rules/showcase.md),
 *     loaded by content.ts and rendered by react-markdown, which turns Markdown into
 *     React elements without injecting raw HTML.
 *   - The tabs follow the WAI-ARIA tabs pattern: role="tablist" / "tab" / "tabpanel",
 *     aria-selected on the chosen tab, and Left/Right arrow keys to move between
 *     tabs (the key handler is on the tab list only, never global).
 *   - Whether the panel is open belongs to the screen (it has the toggle button in
 *     its title row); the panel only reports "close" through onClose.
 *   - A screen can offer more than one explanation (Step 5b: the Loan Tape and its
 *     Product Slotting action). `choices` then draws a switch of toggle buttons
 *     (aria-pressed) above the tabs; the first choice is shown at first.
 */
import { useId, useState, type KeyboardEvent } from "react";
import Markdown from "react-markdown";
import { lookupTerm, screenExplanations, screenTerms, splitExplanation, type ScreenId } from "../content/content";

type Tab = "business" | "technical";
const TABS: { id: Tab; label: string }[] = [
  { id: "business", label: "Business" },
  { id: "technical", label: "Technical" },
];

/** One explanation a screen offers: which file, and the switch button's word. */
export interface ExplainChoice {
  screen: ScreenId;
  label: string;
}

interface ExplainPanelProps {
  /** Which screen's explanation to show, for example "loan-tape". */
  screen: ScreenId;
  /** BUSINESS: other explanations to switch to, with this screen's first (Step 5b). */
  choices?: ExplainChoice[];
  /** The switch's group name, for screen readers ("Explain"). */
  choicesLabel?: string;
  /** Called when the visitor closes the panel. */
  onClose: () => void;
}

/**
 * The glossary card plus its term chips.
 * BUSINESS: "Glossary · WAC: weighted-average coupon ... Why it matters: ...".
 * TECH: each chip is a toggle button (aria-pressed); the card is a live region, so a
 *   screen reader reads the new definition when a chip is pressed.
 */
function GlossaryCard({ terms }: { terms: string[] }) {
  const [selected, setSelected] = useState(terms[0]);
  const entry = lookupTerm(selected);
  return (
    <>
      {entry && (
        <div className="glossary-card" aria-live="polite">
          <span className="eyebrow">Glossary · {entry.term}</span>
          <span>{entry.definition}</span>
          <span className="muted small">Why it matters: {entry.why}</span>
        </div>
      )}
      <div className="term-chips" role="group" aria-label="Glossary terms">
        {terms.map((t) => (
          <button key={t} type="button" className="term-chip" aria-pressed={t === selected}
            onClick={() => setSelected(t)}>
            {t}
          </button>
        ))}
      </div>
    </>
  );
}

/**
 * The explanation panel.
 * BUSINESS: every screen explains itself, in business and technical terms.
 * TECH: useState holds the chosen tab; useId gives unique ids linking each tab to
 *   its panel, so two screens' panels never clash.
 */
export function ExplainPanel({ screen: first, choices, choicesLabel, onClose }: ExplainPanelProps) {
  const [tab, setTab] = useState<Tab>("business");
  const [screen, setScreen] = useState<ScreenId>(first);
  const baseId = useId();
  const sections = splitExplanation(screenExplanations[screen]);

  // TECH: Left/Right move to the other tab and focus it (WAI-ARIA tabs pattern).
  const onTabKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    const next: Tab = tab === "business" ? "technical" : "business";
    setTab(next);
    document.getElementById(`${baseId}-tab-${next}`)?.focus();
  };

  return (
    <aside className="explain-panel" aria-label="Screen explanation">
      <div className="explain-head">
        <span className="panel-title">Explain this screen</span>
        <button type="button" className="icon-btn" aria-label="Close explanation" onClick={onClose}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
            strokeLinecap="round" aria-hidden="true">
            <path d="M6 6l12 12M18 6L6 18" />
          </svg>
        </button>
      </div>
      {choices && choices.length > 1 && (
        <div className="explain-switch" role="group" aria-label={choicesLabel}>
          {choices.map((c) => (
            <button key={c.screen} type="button" className="term-chip" aria-pressed={c.screen === screen}
              onClick={() => setScreen(c.screen)}>
              {c.label}
            </button>
          ))}
        </div>
      )}
      <div role="tablist" aria-label="Explanation" className="explain-tabs" onKeyDown={onTabKey}>
        {TABS.map((t) => (
          <button key={t.id} id={`${baseId}-tab-${t.id}`} type="button" role="tab"
            aria-selected={tab === t.id} aria-controls={`${baseId}-panel`} tabIndex={tab === t.id ? 0 : -1}
            className="explain-tab" onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>
      <div id={`${baseId}-panel`} role="tabpanel" aria-labelledby={`${baseId}-tab-${tab}`} className="explain-body">
        <div className="explain-text">
          <Markdown>{sections[tab]}</Markdown>
        </div>
        {/* TECH: a new key per explanation resets the glossary card to its first term. */}
        <GlossaryCard key={screen} terms={screenTerms[screen]} />
      </div>
    </aside>
  );
}
