/**
 * components/ask/AgentToolsPanel.tsx: the tools the agent can call, and its guardrails.
 *
 * Where it sits: AskTheTapeScreen (right column) -> [AgentToolsPanel]; words from
 *   content/ask-the-tape.json "screen" (tools, guardrails).
 *
 * BUSINESS: a visitor sees the agent's whole reach before asking anything: five
 *   read-only tools, and the checks every call passes. This is what makes the
 *   answers trustworthy: the model can only ask; LoanIQ's code decides and runs.
 * TECH: static content, no data calls. The tool names match backend/app/agent/
 *   tools.py TOOL_SPECS; a unit test checks the two lists agree.
 */
import { askTheTapeContent as words } from "../../content/content";

/** The panel. */
export function AgentToolsPanel() {
  return (
    <section className="side-card" aria-label={words.toolsTitle}>
      <span className="side-card-title">{words.toolsTitle}</span>
      <dl className="tool-list">
        {words.tools.map((t) => (
          <div key={t.name} className="tool-item">
            <dt className="tool-name">{t.name}</dt>
            <dd className="muted small">{t.what}</dd>
          </div>
        ))}
      </dl>
      <span className="side-card-title side-card-divider">{words.guardrailsTitle}</span>
      <ul className="guard-list">
        {words.guardrails.map((g) => (
          <li key={g}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4"
              strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M5 12l4 4 10-10" />
            </svg>
            <span>{g}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
