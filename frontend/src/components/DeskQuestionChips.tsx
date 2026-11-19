/**
 * components/DeskQuestionChips.tsx: the one-click "desk questions" above the grid.
 *
 * Where it sits: GET /api/loans/questions (counts) + content/desk-questions.json
 * (labels) -> Loan Tape screen -> [DeskQuestionChips] -> the grid's ?question= filter.
 *
 * BUSINESS: the questions a trader asks first of every new tape: which loans are
 *   above 125 LTV, in New York or Puerto Rico, 90+ days late or worse, modified, in
 *   forbearance. Each chip shows how many loans answer it; clicking it shows exactly
 *   those loans in the grid (with any column filters the trader has typed), and
 *   clicking it again shows the whole tape. One question at a time, so the count on
 *   the chip and the count in the header always tell the same story.
 * TECH: the rules live on the server (backend/app/config/desk_questions.toml); the
 *   SPA only knows ids and labels. Each chip is a toggle <button> with aria-pressed,
 *   so a screen reader says "LTV over 125, toggle button, pressed". The tooltip is
 *   the glossary entry of the chip's term, in the button's title (a focusable
 *   glossary word inside a button would be a control inside a control).
 */
import type { QuestionCount } from "../api/types";
import { deskQuestionLabels, termTooltip } from "../content/content";
import { formatNumber } from "../grid/columnFormats";
import { GlossaryTerm } from "./GlossaryTerm";

interface DeskQuestionChipsProps {
  /** Counts from the API; null while loading. */
  counts: QuestionCount[] | null;
  /** The id of the chip that is on, or null for none. */
  active: string | null;
  /** BUSINESS: the trader clicked a chip. TECH: called with null to turn it off. */
  onChange: (id: string | null) => void;
}

/**
 * The chip row.
 * BUSINESS: "Desk questions: LTV over 125 · 20, New York · 101, ...".
 * TECH: chips follow the label file's order (the same as the config's, checked by a
 *   back-end test); a count still loading shows "…".
 */
export function DeskQuestionChips({ counts, active, onChange }: DeskQuestionChipsProps) {
  const byId = new Map((counts ?? []).map((c) => [c.id, c.loans]));
  return (
    <div className="chips" role="group" aria-label="Desk questions">
      <span className="muted chips-label">
        <GlossaryTerm term="Desk question">Desk questions</GlossaryTerm>
      </span>
      {deskQuestionLabels.map((q) => {
        const on = active === q.id;
        const n = byId.get(q.id);
        return (
          <button key={q.id} type="button" className="chip" aria-pressed={on}
            title={termTooltip(q.term)} onClick={() => onChange(on ? null : q.id)}>
            {q.label}
            <span className="chip-count">{n === undefined ? "…" : formatNumber(n, "count")}</span>
          </button>
        );
      })}
    </div>
  );
}
