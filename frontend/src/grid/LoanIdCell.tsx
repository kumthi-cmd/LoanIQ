/**
 * grid/LoanIdCell.tsx: the Loan ID cell, which opens the loan's slot card on hover.
 *
 * Where it sits: buildColumnDefs (loan_id) -> [LoanIdCell] -> LoanTapeScreen's onLoanHover
 * -> SlotCard (GET /api/loans/{loan_id}/slots).
 *
 * BUSINESS: once the tape is slotted, a trader hovers a loan ID to see where that loan
 *   can go: its pool coupons and spec stories, or why it is not slotted. A dotted
 *   underline marks the ID as hoverable.
 * TECH: an AG Grid cell renderer is a React component AG Grid draws inside each cell;
 *   it gets the cell's value and the grid's `context` object (LoanGrid passes the
 *   screen's onLoanHover there). Before a run onLoanHover is absent, and the cell is
 *   plain text. Keyboard users get the same card from the grid's cell focus
 *   (LoanGrid.tsx), so the cell itself adds no extra tab stop.
 */
import type { CustomCellRendererProps } from "ag-grid-react";
import type { LoanRow } from "../api/types";

/** TECH: what LoanGrid puts in AG Grid's context for the cells. */
export interface LoanGridContext {
  /** Show the card for a loan at a box on screen; null hides it. Absent before slotting. */
  onLoanHover?: (loanId: string | null, anchor: DOMRect | null) => void;
}

/**
 * The Loan ID cell.
 * BUSINESS: the loan's key, and the door to its slot card.
 */
export function LoanIdCell(props: CustomCellRendererProps<LoanRow, string, LoanGridContext>) {
  const id = props.value ?? "";
  const hover = props.context?.onLoanHover;
  if (!hover) return <span>{id}</span>;
  return (
    <span className="loan-id-hover" data-loan-id={id}
      onMouseEnter={(e) => hover(id, e.currentTarget.getBoundingClientRect())}
      onMouseLeave={() => hover(null, null)}>
      {id}
    </span>
  );
}
