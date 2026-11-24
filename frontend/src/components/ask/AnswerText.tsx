/**
 * components/ask/AnswerText.tsx: the agent's answer, with clickable loan IDs.
 *
 * Where it sits: AnswerTurn -> [AnswerText] -> react-markdown; a loan ID -> LoanDrawer.
 *
 * BUSINESS: "19 New York loans ... **$1,910,592** of current UPB". The model writes
 *   short Markdown (bold numbers, lists). Every loan ID in it opens that loan.
 * TECH: react-markdown turns Markdown into React elements and never injects raw HTML,
 *   so an answer cannot add scripts or styles to the page. Loan IDs are first made
 *   into "#loan-..." links (resultFormat.linkLoanIds), and the "a" component swaps
 *   those links for buttons. Any other link opens in a new tab, marked noopener.
 */
import Markdown, { type Components } from "react-markdown";
import { linkLoanIds, loanIdFromHref } from "../../ask/resultFormat";

interface AnswerTextProps {
  text: string;
  /** BUSINESS: open the loan drawer for this loan ID. */
  onOpenLoan: (loanId: string) => void;
}

/** The answer's Markdown. */
export function AnswerText({ text, onOpenLoan }: AnswerTextProps) {
  // TECH: built per render because it closes over onOpenLoan; the cost is tiny.
  const components: Components = {
    a: ({ href, children }) => {
      const loanId = loanIdFromHref(href);
      if (loanId) {
        return (
          <button type="button" className="loan-id-link" onClick={() => onOpenLoan(loanId)}>
            {children}
          </button>
        );
      }
      return <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>;
    },
  };
  return (
    <div className="answer-text">
      <Markdown components={components}>{linkLoanIds(text)}</Markdown>
    </div>
  );
}
