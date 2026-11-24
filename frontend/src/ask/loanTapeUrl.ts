/**
 * ask/loanTapeUrl.ts: the Loan Tape's address for "same filter", both ways.
 *
 * Where it sits:
 *   Ask the Tape result -> [loanTapeUrl] -> "/?filter=...&sort=..." -> Loan Tape
 *   Loan Tape -> [readLoanTapeParams] -> LoanGrid's initial filter and sort
 *
 * BUSINESS: "Open in Loan Tape" opens the full grid on exactly the loans an answer
 *   was about. Because the filter is in the URL, the link can be bookmarked or sent
 *   to a colleague, and the browser's Back button returns to the answer.
 * TECH:
 *   - The filter is AG Grid's own filter model as JSON, made by the back end from
 *     the answer's SQL (backend/app/agent/loan_tape_link.py). It is data, never
 *     SQL: the grid sends it to /api/loans, which checks every column and binds
 *     every value (loan_query.py), as for a filter the trader types.
 *   - URLSearchParams escapes the JSON so quotes and braces travel safely.
 *   - Anything in the URL is untrusted (anyone can edit it), so reading it back
 *     accepts only a JSON object for filter, "col:asc|desc" pairs for sort, and a
 *     known desk-question id. Anything else is ignored, never guessed at.
 */
import type { SortModelItem } from "ag-grid-community";
import type { LoanTapeLink } from "../api/types";

/** BUSINESS: the Loan Tape route. TECH: matches nav.ts. */
const LOAN_TAPE_PATH = "/";

/**
 * The Loan Tape URL for one answer's link, or null when it cannot open.
 * BUSINESS: null means the answer's filter has no column-filter form (link.reason
 *   says why), so the button is shown disabled instead.
 */
export function loanTapeUrl(link: LoanTapeLink | null | undefined): string | null {
  if (!link || !link.filter) return null;
  const params = new URLSearchParams();
  if (Object.keys(link.filter).length > 0) params.set("filter", JSON.stringify(link.filter));
  if (link.sort) params.set("sort", link.sort);
  const query = params.toString();
  return query ? `${LOAN_TAPE_PATH}?${query}` : LOAN_TAPE_PATH;
}

/** What the Loan Tape reads from its URL. TECH: all null when the URL has nothing valid. */
export interface LoanTapeParams {
  filter: Record<string, unknown> | null;
  sort: SortModelItem[];
  question: string | null;
}

/**
 * Read the Loan Tape's filter, sort and desk question from the URL.
 * TECH: knownQuestions are the desk-question ids (content/desk-questions.json);
 *   knownColumns the tape's columns, so a sort on an unknown column is dropped.
 */
export function readLoanTapeParams(
  params: URLSearchParams,
  knownQuestions: string[],
  knownColumns: string[],
): LoanTapeParams {
  return {
    filter: parseFilter(params.get("filter")),
    sort: parseSort(params.get("sort"), knownColumns),
    question: knownQuestions.find((q) => q === params.get("question")) ?? null,
  };
}

/** TECH: a JSON object, or null for anything else (bad JSON, an array, a number). */
function parseFilter(raw: string | null): Record<string, unknown> | null {
  if (!raw) return null;
  try {
    const value: unknown = JSON.parse(raw);
    return typeof value === "object" && value !== null && !Array.isArray(value)
      ? (value as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

/** TECH: "current_upb:desc,fico:asc" -> AG Grid sort model; unknown parts are dropped. */
function parseSort(raw: string | null, knownColumns: string[]): SortModelItem[] {
  if (!raw) return [];
  return raw.split(",").flatMap((part) => {
    const [colId, dir] = part.split(":");
    return knownColumns.includes(colId) && (dir === "asc" || dir === "desc") ? [{ colId, sort: dir }] : [];
  });
}

/**
 * The columns a URL filter or sort uses.
 * BUSINESS: the Loan Tape shows these even if they are not among its default columns,
 *   so the trader can see (and clear) every filter that is on.
 */
export function columnsInUse(p: LoanTapeParams): string[] {
  return [...Object.keys(p.filter ?? {}), ...p.sort.map((s) => s.colId)];
}
