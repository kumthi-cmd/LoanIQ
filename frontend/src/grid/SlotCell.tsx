/**
 * grid/SlotCell.tsx: the Slot cell: "UMBS 30Y 2.5 / 3.0", or a grey "Not slotted".
 *
 * Where it sits: GET /api/loans (slot) -> buildColumnDefs -> [SlotCell].
 *
 * BUSINESS: where the loan can go, at its down and up coupons. A loan no agency pool
 *   takes reads "Not slotted" in grey; Spec Stories beside it says why.
 * TECH: the "Not slotted" text comes from content/slotting.json, as the server writes it.
 */
import type { CustomCellRendererProps } from "ag-grid-react";
import type { LoanRow } from "../api/types";
import { slottingCellWords } from "../content/content";

/** The Slot cell. */
export function SlotCell(props: CustomCellRendererProps<LoanRow, string | null>) {
  const value = props.value ?? "";
  return <span className={value === slottingCellWords.notSlotted ? "muted" : undefined}>{value}</span>;
}
