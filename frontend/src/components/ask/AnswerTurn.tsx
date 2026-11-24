/**
 * components/ask/AnswerTurn.tsx: one question and its answer in the conversation.
 *
 * Where it sits: AskTheTapeScreen -> [AnswerTurn] -> ToolChips, AnswerText,
 *   QueryResultTable (one per query the agent ran).
 *
 * BUSINESS: as on the design board: the question on the right; under it "Save query"
 *   (or "Saved as <tag>"); then the agent's tool chips, its answer, a notice if
 *   built-in rules answered, and the rows behind it with "Open in Loan Tape".
 * TECH: everything shown comes from the Turn (ask/conversation.ts). Saving is only
 *   offered once the answer is complete and at least one query ran, because what is
 *   saved is that query's SQL. A rerun turn is already saved and says so.
 */
import type { ColumnInfo } from "../../api/types";
import { resultSteps, type Turn } from "../../ask/conversation";
import { askTheTapeContent as words } from "../../content/content";
import { AnswerText } from "./AnswerText";
import { QueryResultTable } from "./QueryResultTable";
import { ToolChips } from "./ToolChips";

interface AnswerTurnProps {
  turn: Turn;
  columns: Map<string, ColumnInfo>;
  /** The saved tag when this turn's queries are saved, else null. */
  savedTag: string | null;
  /** Save this turn's queries; absent when there is nothing to save. */
  onSave?: () => void;
  onOpenLoan: (loanId: string) => void;
}

/** TECH: the bookmark icon from the design board; decorative, so hidden from screen readers. */
function BookmarkIcon({ filled }: { filled: boolean }) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill={filled ? "currentColor" : "none"} stroke="currentColor"
      strokeWidth="2" strokeLinejoin="round" aria-hidden="true">
      <path d="M6 3h12v18l-6-4-6 4z" />
    </svg>
  );
}

/** One turn. */
export function AnswerTurn({ turn, columns, savedTag, onSave, onOpenLoan }: AnswerTurnProps) {
  const results = resultSteps(turn);
  const notice = turn.answer?.notice ?? turn.fallbackNotice;
  return (
    <article className="turn" aria-label={`Question: ${turn.question}`}>
      <div className="question-bubble">{turn.question}</div>
      <div className="question-meta">
        {savedTag ? (
          <span className="saved-as">
            <BookmarkIcon filled />
            <span>{words.savedAs}</span>
            <span className="saved-tag">{savedTag}</span>
          </span>
        ) : (
          onSave && (
            <button type="button" className="btn btn-small" onClick={onSave}>
              <BookmarkIcon filled={false} />
              {words.saveQuery}
            </button>
          )
        )}
      </div>

      <div className="answer">
        <span className="answer-avatar" aria-hidden="true">AI</span>
        <div className="answer-body">
          <ToolChips steps={turn.steps} />
          {turn.status === "running" && !turn.answer && (
            <p className="muted" role="status">{words.thinking}</p>
          )}
          {turn.error && (
            <div role="alert" className="grid-error">{words.errorPrefix}{turn.error}</div>
          )}
          {turn.answer && <AnswerText text={turn.answer.text} onOpenLoan={onOpenLoan} />}
          {notice && <p className="answer-notice small">{notice}</p>}
          {turn.status !== "running" && results.map((s) => (
            <QueryResultTable key={s.result.query_id} queryId={s.result.query_id}
              initial={turn.results?.[s.result.query_id]} link={s.result.loan_tape}
              columns={columns} onOpenLoan={onOpenLoan} />
          ))}
        </div>
      </div>
    </article>
  );
}
