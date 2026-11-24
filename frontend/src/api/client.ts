/**
 * api/client.ts: the JSON API calls the screens make.
 *
 * Where it sits: Loan Tape and Ask the Tape screens -> [client] -> /api/... -> FastAPI
 * (backend/app/main.py, backend/app/agent/api.py)
 *
 * BUSINESS: column headers, the headline numbers, the three summary panels, the
 *   desk-question counts, the tape line, and one page of loans at a time. For Ask
 *   the Tape (Step 4b): who is answering, every row behind an answer, one loan for
 *   the drawer, and a saved query's rerun. The streamed question itself is in
 *   ask/askStream.ts, because it is read event by event, not as one JSON body.
 * TECH: plain fetch() with relative URLs, so the same code works through Vite's dev
 *   proxy and against the built app served by FastAPI. A non-2xx answer throws an
 *   ApiError carrying the server's message (for example a 400 for a bad filter),
 *   so callers never treat an error body as data.
 */
import type {
  AskStatus, Breakdowns, ColumnInfo, LoanRecord, LoansPage, QuestionCount, RerunRequest, StoredQuery, Summary,
  TapeInfo,
} from "./types";

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
  return readJson<T>(await fetch(url, { signal }));
}

/**
 * POST a JSON body, read a JSON answer.
 * BUSINESS: used to rerun a saved query (Step 4b).
 * TECH: same error handling as getJson.
 */
async function postJson<T>(url: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  return readJson<T>(res);
}

/**
 * A response's JSON, or an ApiError with the server's message.
 * TECH: FastAPI errors look like {"detail": "..."}; fall back to the status text.
 *   A validation error (422) has a list as detail, so it falls back too.
 */
export async function readJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
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

// ---------------------------------------------------------------------------
// Ask the Tape (Step 4b). None of these calls an AI model.
// ---------------------------------------------------------------------------

/** BUSINESS: is the AI model answering, or built-in rules (the Offline banner)? */
export const fetchAskStatus = (signal?: AbortSignal) => getJson<AskStatus>("/api/ask/status", signal);

/** BUSINESS: every row behind one answer. TECH: 404 once the result expires (1 hour). */
export const fetchStoredQuery = (queryId: string, signal?: AbortSignal) =>
  getJson<StoredQuery>(`/api/ask/queries/${encodeURIComponent(queryId)}`, signal);

/** BUSINESS: one loan, every field, for the loan drawer. TECH: the agent's get_loan tool. */
export const fetchLoanRecord = (loanId: string, signal?: AbortSignal) =>
  getJson<LoanRecord>(`/api/ask/loans/${encodeURIComponent(loanId)}`, signal);

/**
 * BUSINESS: rerun a saved query on the tape, without the model.
 * TECH: the server checks the SQL with the same guardrails as the model's; a refused
 *   query is an ApiError(400) with the reason.
 */
export const rerunQuery = (body: RerunRequest, signal?: AbortSignal) =>
  postJson<StoredQuery>("/api/ask/rerun", body, signal);
