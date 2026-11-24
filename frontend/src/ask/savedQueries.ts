/**
 * ask/savedQueries.ts: the last 5 saved queries, kept in this browser.
 *
 * Where it sits: AnswerTurn "Save query" -> [savedQueries] -> localStorage
 *   -> SavedQueries panel -> click -> POST /api/ask/rerun (no model).
 *
 * BUSINESS: the desk asks the same questions of every tape. Saving an answer keeps
 *   its SQL under a short tag ("LTV > 125"); one click reruns it on the tape in
 *   milliseconds, at no AI cost, with exactly the same rule.
 * TECH:
 *   - localStorage is the browser's small key-value store, private to this site
 *     and this browser. It suits a per-visitor convenience: nothing is shared, and
 *     nothing on the server needs to know.
 *   - Storage can be missing or refuse to work (a private window, blocked site
 *     data). Every read and write is wrapped in try/catch, so the screen still
 *     works; saved queries simply do not survive a reload.
 *   - What is saved is the SQL as the server showed it (display SQL). On rerun it
 *     goes through the same guardrails as the model's SQL, so a hand-edited entry
 *     can do nothing the agent could not.
 *   - Data read back is checked field by field; anything malformed is dropped.
 */

/** BUSINESS: how many saved queries the panel keeps (the design board's "Last 5"). */
export const MAX_SAVED = 5;
/** TECH: the localStorage key; ".v1" lets a later format change start clean. */
export const STORAGE_KEY = "loaniq.askTheTape.savedQueries.v1";

/** One query an answer ran. */
export interface SavedSql {
  sql: string;
  title: string;
}

/**
 * One saved query.
 * BUSINESS: tag is the short label on the button; question is the full question,
 *   shown as the button's tooltip.
 */
export interface SavedQuery {
  tag: string;
  question: string;
  queries: SavedSql[];
}

/** TECH: true for an object with the SavedQuery shape (data from storage is untrusted). */
function isSavedQuery(v: unknown): v is SavedQuery {
  if (typeof v !== "object" || v === null) return false;
  const q = v as Record<string, unknown>;
  return (
    typeof q.tag === "string" && typeof q.question === "string" && Array.isArray(q.queries) &&
    q.queries.length > 0 &&
    q.queries.every((s) => typeof s === "object" && s !== null &&
      typeof (s as SavedSql).sql === "string" && typeof (s as SavedSql).title === "string")
  );
}

/** Read the saved list, newest first. TECH: [] when storage is empty, blocked or corrupt. */
export function loadSaved(): SavedQuery[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter(isSavedQuery).slice(0, MAX_SAVED) : [];
  } catch {
    return [];
  }
}

/** Write the list. TECH: a failed write is ignored; the in-memory list still works. */
export function storeSaved(list: SavedQuery[]): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
  } catch {
    // TECH: storage full or blocked; nothing else to do.
  }
}

/** TECH: two saved queries are the same if they run the same SQL. */
const sameSql = (a: SavedQuery, b: SavedQuery) =>
  a.queries.map((q) => q.sql).join("\n;\n") === b.queries.map((q) => q.sql).join("\n;\n");

/**
 * Add a query at the front, dropping any earlier copy and anything past MAX_SAVED.
 * BUSINESS: saving again moves it to the front instead of filling the list with copies.
 */
export function addSaved(list: SavedQuery[], query: SavedQuery): SavedQuery[] {
  return [query, ...list.filter((q) => !sameSql(q, query))].slice(0, MAX_SAVED);
}

/** The saved entry running the same SQL, if any (the answer then shows "Saved as <tag>"). */
export function findSaved(list: SavedQuery[], query: SavedQuery): SavedQuery | undefined {
  return list.find((q) => sameSql(q, query));
}

/**
 * The tag for a saved query: the agent's title for its first query, else the
 * question, cut to 40 characters.
 * BUSINESS: "LTV over 125, highest first" reads better on a button than the SQL.
 */
export function tagFor(question: string, queries: SavedSql[]): string {
  const text = (queries[0]?.title || question).trim();
  return text.length > 40 ? `${text.slice(0, 39)}…` : text;
}
