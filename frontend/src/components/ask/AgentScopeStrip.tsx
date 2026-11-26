/**
 * components/ask/AgentScopeStrip.tsx: "Knows: Tape ✓ · Slotting ✓ · BestEx –", the desk
 * stages Ask the Tape knows right now.
 *
 * Where it sits: GET /api/ask/status (stages) -> AskTheTapeScreen -> [AgentScopeStrip].
 *
 * BUSINESS: the agent's scope grows as the desk works the tape (Step 5c): it knows
 *   the tape from the start, and each later stage once the desk has run it. The strip
 *   shows a visitor where that stands, so "how many loans are slotted?" before a run
 *   gets a "not run yet" they can see coming, and BestEx and the later stages are
 *   plainly not there yet.
 * TECH: a list (ul) named for screen readers; each stage's state is spoken in words
 *   ("Slotting, not run yet") and the ✓ and – marks are hidden from them. A stage's
 *   title tooltip says the same. Words from content/ask-the-tape.json "scope".
 *   Nothing shows until the status arrives.
 */
import type { AskStatus } from "../../api/types";
import { askTheTapeContent } from "../../content/content";

const words = askTheTapeContent.scope;
type StageId = keyof typeof words.stages;
type StateId = keyof typeof words.states;

/** The strip, or nothing before the status is known. */
export function AgentScopeStrip({ status }: { status: AskStatus | null }) {
  const stages = status?.stages ?? [];
  if (stages.length === 0) return null;
  return (
    <div className="scope-strip">
      <span className="eyebrow">{words.label}</span>
      <ul aria-label={words.listName}>
        {stages.map((s) => {
          const label = words.stages[s.id as StageId] ?? s.id;
          const state = words.states[s.state as StateId] ?? s.state;
          return (
            <li key={s.id} className={`scope-stage scope-${s.state}`} title={`${label}: ${state}`}>
              <span>{label}</span>
              <span aria-hidden="true">{s.state === "known" ? "✓" : "–"}</span>
              <span className="visually-hidden">, {state}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
