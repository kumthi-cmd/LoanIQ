/**
 * components/ask/SavedQueriesPanel.tsx: the last 5 saved queries, each one click to rerun.
 *
 * Where it sits: AskTheTapeScreen (right column) -> [SavedQueriesPanel]
 *   -> click -> screen reruns the SQL through POST /api/ask/rerun (no model).
 *
 * BUSINESS: the questions the desk asks of every tape, one click away, answered in
 *   milliseconds at no AI cost. The tag is on the button; the full question is its
 *   tooltip and its accessible name ("Rerun: ...").
 * TECH: the list itself lives in the screen (it also decides "Saved as" on each
 *   answer) and in localStorage (ask/savedQueries.ts); this panel only draws it.
 */
import type { SavedQuery } from "../../ask/savedQueries";
import { askTheTapeContent as words } from "../../content/content";

interface SavedQueriesPanelProps {
  saved: SavedQuery[];
  onRerun: (query: SavedQuery) => void;
  /** TECH: true while a question or rerun is running, so reruns wait their turn. */
  busy: boolean;
}

/** The panel. */
export function SavedQueriesPanel({ saved, onRerun, busy }: SavedQueriesPanelProps) {
  return (
    <section className="side-card" aria-label={words.savedTitle}>
      <div className="side-card-head">
        <span className="side-card-title">{words.savedTitle}</span>
        <span className="muted small">{words.savedHint}</span>
      </div>
      {saved.length === 0 ? (
        <p className="muted small">{words.savedEmpty}</p>
      ) : (
        <div className="saved-list">
          {saved.map((q) => (
            <button key={q.tag + q.queries[0].sql} type="button" className="saved-tag saved-button"
              title={q.question} aria-label={`Rerun: ${q.question}`} disabled={busy}
              onClick={() => onRerun(q)}>
              {q.tag}
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
