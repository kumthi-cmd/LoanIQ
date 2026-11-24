/**
 * ask/resultFormat.ts: how Ask the Tape shows result cells, loan fields and loan IDs.
 *
 * Where it sits: QueryResultTable and LoanDrawer -> [resultFormat] -> grid/columnFormats.ts
 *   AnswerText -> [linkLoanIds] -> react-markdown
 *
 * BUSINESS: an answer's table reads like the Loan Tape: money with commas, rates with
 *   3 decimals, LTV with 2 (.claude/rules/frontend.md). Loan IDs anywhere in an
 *   answer open the loan drawer.
 * TECH:
 *   - A result column that is a tape column uses that column's format
 *     (columnFormats.ts). A column the agent computed (an alias such as "wac" or
 *     "loans") has no known unit, so it shows its value plainly: whole numbers with
 *     commas, other numbers to at most 3 decimals. Nothing is rounded silently to
 *     fewer decimals than the tape's own formats use.
 *   - A loan ID is LN followed by 8 digits (backend tools.py LOAN_ID_PATTERN).
 */
import type { ColumnInfo } from "../api/types";
import { formatBoolean, formatDate, formatNumber, numberFormatFor } from "../grid/columnFormats";

/** BUSINESS: a loan's key, as the tape writes it. TECH: global, for replace(). */
export const LOAN_ID_RE = /\bLN\d{8}\b/g;
/** TECH: the result column that holds loan IDs. */
export const LOAN_ID_COLUMN = "loan_id";

// TECH: for computed columns: commas, at most 3 decimals.
const PLAIN = new Intl.NumberFormat("en-US", { maximumFractionDigits: 3 });

/**
 * One cell as text.
 * TECH: columns maps tape column name -> ColumnInfo (kind). null/undefined -> "".
 */
export function formatCell(column: string, value: unknown, columns: Map<string, ColumnInfo>): string {
  if (value === null || value === undefined) return "";
  const info = columns.get(column);
  if (info?.kind === "number") return formatNumber(value, numberFormatFor(column));
  if (info?.kind === "date") return formatDate(value);
  if (info?.kind === "boolean" || typeof value === "boolean") return formatBoolean(value);
  if (typeof value === "number") return PLAIN.format(value);
  return String(value);
}

/** BUSINESS: numbers right-aligned so digits line up. TECH: for the cell's CSS class. */
export function isNumericColumn(column: string, columns: Map<string, ColumnInfo>, sample: unknown): boolean {
  const info = columns.get(column);
  return info ? info.kind === "number" : typeof sample === "number";
}

/** The readable header for a result column: the tape's label, else the name as written. */
export function columnLabel(column: string, columns: Map<string, ColumnInfo>): string {
  return columns.get(column)?.label ?? column;
}

/**
 * Turn every loan ID in Markdown text into a link "#loan-LN........".
 * BUSINESS: "LN72972382 is the largest" -> the ID opens the loan drawer.
 * TECH: the answer is Markdown, so the IDs become Markdown links, and AnswerText
 *   draws any link to "#loan-..." as a button. An ID already inside a link or code
 *   span would be rare in an answer; it is wrapped like any other.
 */
export function linkLoanIds(markdown: string): string {
  return markdown.replace(LOAN_ID_RE, (id) => `[${id}](#loan-${id})`);
}

/** TECH: the loan ID from a "#loan-LN........" link, or null for any other link. */
export function loanIdFromHref(href: string | undefined): string | null {
  const m = href ? /^#loan-(LN\d{8})$/.exec(href) : null;
  return m ? m[1] : null;
}
