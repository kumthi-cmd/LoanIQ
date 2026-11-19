/**
 * api/client.ts: the loan API calls the Loan Tape screen makes.
 *
 * Where it sits: Loan Tape screen -> [client] -> /api/... -> FastAPI (backend/app/main.py)
 *
 * BUSINESS: column headers, the headline numbers, the three summary panels, the
 *   desk-question counts, the tape line, and one page of loans at a time.
 * TECH: plain fetch() with relative URLs, so the same code works through Vite's dev
 *   proxy and against the built app served by FastAPI. A non-2xx answer throws an
 *   ApiError carrying the server's message (for example a 400 for a bad filter),
 *   so callers never treat an error body as data.
 */
import type { Breakdowns, ColumnInfo, LoansPage, QuestionCount, Summary, TapeInfo } from "./types";

/**
 * An API call that did not succeed.
 * BUSINESS: lets the screen say "the server refused this filter" instead of showing
 *   an empty grid as if no loans matched.
 * TECH: status is the HTTP status; message is FastAPI's "detail" when there is one.
 */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * GET a JSON resource.
 * BUSINESS: the one place every screen talks to the server.
 * TECH: signal lets a caller cancel (AbortController) when the screen unmounts.
 */
async function getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(url, { signal });
  if (!res.ok) {
    // TECH: FastAPI errors look like {"detail": "..."}; fall back to the status text.
    const body = await res.json().catch(() => null);
    const detail = body && typeof body.detail === "string" ? body.detail : res.statusText;
    throw new ApiError(res.status, detail || `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

/** BUSINESS: the grid's columns, in tape order. TECH: GET /api/loans/columns. */
export const fetchColumns = (signal?: AbortSignal) =>
  getJson<ColumnInfo[]>("/api/loans/columns", signal);

/** BUSINESS: the whole tape's headline numbers. TECH: GET /api/loans/summary. */
export const fetchSummary = (signal?: AbortSignal) =>
  getJson<Summary>("/api/loans/summary", signal);

/** BUSINESS: program mix, note-rate buckets and MBA delinquency. TECH: GET /api/loans/breakdowns. */
export const fetchBreakdowns = (signal?: AbortSignal) =>
  getJson<Breakdowns>("/api/loans/breakdowns", signal);

/** BUSINESS: how many loans answer each desk question. TECH: GET /api/loans/questions. */
export const fetchQuestionCounts = (signal?: AbortSignal) =>
  getJson<QuestionCount[]>("/api/loans/questions", signal);

/** BUSINESS: "41 fields · 6 fictional sellers". TECH: GET /api/tape. */
export const fetchTapeInfo = (signal?: AbortSignal) => getJson<TapeInfo>("/api/tape", signal);

/**
 * BUSINESS: one block of loans for the grid.
 * TECH: GET /api/loans?<query>. query is built by grid/loanQuery.ts.
 */
export const fetchLoans = (query: URLSearchParams, signal?: AbortSignal) =>
  getJson<LoansPage>(`/api/loans?${query.toString()}`, signal);
