/**
 * screens/AskTheTapeScreen.tsx: the Ask the Tape screen (route "/ask", Step 4b).
 *
 * Where it sits: the Tape stage of the desk's flow:
 *   loan tape -> [ask the tape] -> slotting -> best execution -> positions -> pools
 *   The engine behind it is Step 4a (backend/app/agent/, content/agent.md).
 *
 * BUSINESS: a trader asks the tape plain-English questions and gets answers in
 *   seconds, each with the tools the agent called, the SQL that ran, and the loans
 *   behind it. From an answer they can open a loan, open the same filter in the
 *   Loan Tape, or save the query to rerun later without the model. A banner says
 *   when built-in rules ("Offline") are answering instead of the AI model.
 *   Layout follows the "Ask the Tape" design board: the conversation on the left,
 *   saved queries and the agent's tools and guardrails on the right.
 * TECH:
 *   - One question = one Turn (ask/conversation.ts), filled in event by event from
 *     the POST /api/ask stream (ask/askStream.ts). Only one question runs at a time;
 *     "New thread" cancels it (AbortController) and clears the conversation.
 *   - Each question is sent on its own: the agent has no memory of earlier turns, so
 *     every answer can be checked by itself (Step 4a's design).
 *   - On first draw: the tape's columns (labels and formats for tables and the loan
 *     drawer) and the status for the Offline banner and, from Step 5c, the scope
 *     strip (which desk stages the agent knows). Status is asked again after every
 *     answer, since a limit can be reached mid-session.
 *   - ?q= in the URL (from the header box or Ctrl K) fills the question box and
 *     focuses it, but does not send: no model call until the visitor presses Send.
 *     The effect runs on every navigation (location.key), so Ctrl K works again
 *     while already on this screen.
 *   - Saved queries live in the screen's state and in localStorage (savedQueries.ts).
 *   - The Agent mark beside the title (Step 4d) opens how the agent works.
 */
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { useLocation, useSearchParams } from "react-router";
import { fetchAskStatus, fetchColumns, rerunQuery } from "../api/client";
import type { AskStatus, ColumnInfo, StoredQuery } from "../api/types";
import { askTheTape } from "../ask/askStream";
import { applyEvent, failTurn, newTurn, rerunTurn, resultSteps, type Turn } from "../ask/conversation";
import {
  addSaved, findSaved, loadSaved, storeSaved, tagFor, type SavedQuery,
} from "../ask/savedQueries";
import { AgentMark } from "../components/AgentMark";
import { AgentToolsPanel } from "../components/ask/AgentToolsPanel";
import { AnswerTurn } from "../components/ask/AnswerTurn";
import { LoanDrawer } from "../components/ask/LoanDrawer";
import { AgentScopeStrip } from "../components/ask/AgentScopeStrip";
import { OfflineBanner } from "../components/ask/OfflineBanner";
import { SavedQueriesPanel } from "../components/ask/SavedQueriesPanel";
import { ExplainPanel } from "../components/ExplainPanel";
import { askTheTapeContent as words } from "../content/content";

/**
 * What a turn would be saved as, or null if it ran no query.
 * BUSINESS: a saved query is the SQL of every query the answer ran, under one tag.
 */
export function savedQueryFor(turn: Turn): SavedQuery | null {
  if (turn.status !== "done") return null;
  const queries = resultSteps(turn).flatMap((s) =>
    s.result.sql ? [{ sql: s.result.sql, title: s.result.title ?? "" }] : []);
  if (queries.length === 0) return null;
  return { tag: tagFor(turn.question, queries), question: turn.question, queries };
}

/**
 * The Ask the Tape screen.
 * TECH: useRef holds values that must survive redraws without causing one: the
 *   running question's AbortController and the next turn number.
 */
export function AskTheTapeScreen() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [status, setStatus] = useState<AskStatus | null>(null);
  const [columns, setColumns] = useState<ColumnInfo[]>([]);
  const [saved, setSaved] = useState<SavedQuery[]>(loadSaved);
  const [drawerLoan, setDrawerLoan] = useState<string | null>(null);
  const [explainOpen, setExplainOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const running = useRef<AbortController | null>(null);
  const nextId = useRef(1);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [searchParams] = useSearchParams();
  const location = useLocation();

  const columnMap = useMemo(() => new Map(columns.map((c) => [c.name, c])), [columns]);

  // TECH: ask the server who is answering; a failure just leaves the banner off.
  const refreshStatus = useCallback(() => {
    fetchAskStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    fetchColumns(ctrl.signal).then(setColumns).catch(() => setColumns([]));
    refreshStatus();
    return () => {
      ctrl.abort();
      running.current?.abort(); // TECH: leaving the screen stops a running question
    };
  }, [refreshStatus]);

  // BUSINESS: a question from the header box or Ctrl K is filled in, ready to send.
  useEffect(() => {
    const q = searchParams.get("q");
    if (q) setInput(q);
    inputRef.current?.focus();
    // TECH: location.key changes on every navigation, even to the same URL.
  }, [location.key, searchParams]);

  /** Replace one turn by id. TECH: functional setState, safe while events stream in. */
  const updateTurn = useCallback((id: string, change: (t: Turn) => Turn) => {
    setTurns((ts) => ts.map((t) => (t.id === id ? change(t) : t)));
  }, []);

  /**
   * Send one question and stream its answer into a new turn.
   * TECH: an abort (New thread, leaving the screen) is not an error to show.
   */
  const ask = useCallback(async (question: string) => {
    const text = question.trim();
    if (!text || running.current) return;
    const id = `t${nextId.current++}`;
    const ctrl = new AbortController();
    running.current = ctrl;
    setBusy(true);
    setInput("");
    setTurns((ts) => [...ts, newTurn(id, text)]);
    try {
      await askTheTape({ question: text }, (ev) => updateTurn(id, (t) => applyEvent(t, ev)), ctrl.signal);
      updateTurn(id, (t) => (t.status === "running" ? { ...t, status: "done" } : t));
    } catch (e) {
      if (!ctrl.signal.aborted) updateTurn(id, (t) => failTurn(t, (e as Error).message));
    } finally {
      if (running.current === ctrl) {
        running.current = null;
        setBusy(false);
      }
      refreshStatus();
    }
  }, [refreshStatus, updateTurn]);

  /**
   * Rerun a saved query: its SQL again through POST /api/ask/rerun, no model.
   * BUSINESS: the answer appears as a new turn that says no model was called.
   */
  const rerun = useCallback(async (query: SavedQuery) => {
    if (running.current) return;
    const id = `t${nextId.current++}`;
    const ctrl = new AbortController();
    running.current = ctrl;
    setBusy(true);
    setTurns((ts) => [...ts, newTurn(id, query.question)]);
    try {
      const results: StoredQuery[] = [];
      for (const q of query.queries) results.push(await rerunQuery(q, ctrl.signal));
      updateTurn(id, () => rerunTurn(id, query.question, results, words.rerunNote));
    } catch (e) {
      if (!ctrl.signal.aborted) updateTurn(id, (t) => failTurn(t, (e as Error).message));
    } finally {
      if (running.current === ctrl) {
        running.current = null;
        setBusy(false);
      }
    }
  }, [updateTurn]);

  /** BUSINESS: keep this answer's queries in the Saved queries panel (last 5). */
  const save = useCallback((query: SavedQuery) => {
    setSaved((list) => {
      const next = addSaved(list, query);
      storeSaved(next);
      return next;
    });
  }, []);

  /** BUSINESS: start over. TECH: cancels a running question first. */
  const newThread = () => {
    running.current?.abort();
    running.current = null;
    setBusy(false);
    setTurns([]);
    setInput("");
    inputRef.current?.focus();
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    void ask(input);
  };
  // TECH: Enter sends, Shift+Enter starts a new line, as in most chat boxes.
  const onInputKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void ask(input);
    }
  };

  return (
    <div className="screen">
      <div className="screen-title-row">
        <div className="screen-title">
          <span className="eyebrow">{words.eyebrow}</span>
          {/* BUSINESS: the Agent mark says Claude answers here; click it to see how.
              TECH: beside the h2, not inside it, so the heading stays "Ask the Tape". */}
          <div className="screen-title-heading">
            <h2>Ask the Tape</h2>
            <AgentMark />
          </div>
        </div>
        <span className="muted tape-line">{words.tagline}</span>
        <div className="title-actions">
          <button type="button" className="btn" onClick={newThread}>New thread</button>
          <button type="button" className="btn btn-accent" aria-expanded={explainOpen}
            onClick={() => setExplainOpen((o) => !o)}>
            {explainOpen ? "Hide explanation" : "Explain this screen"}
          </button>
        </div>
      </div>

      <AgentScopeStrip status={status} />
      <OfflineBanner status={status} />

      <div className="screen-body">
        <div className="screen-main ask-layout">
          <section className="conversation" aria-label="Conversation">
            <div className="turns" aria-live="polite">
              {turns.length === 0 && <p className="muted ask-empty">{words.emptyState}</p>}
              {turns.map((t) => {
                const candidate = t.rerun ? null : savedQueryFor(t);
                const savedEntry = candidate ? findSaved(saved, candidate) : undefined;
                return (
                  <AnswerTurn key={t.id} turn={t} columns={columnMap}
                    savedTag={savedEntry?.tag ?? null}
                    onSave={candidate ? () => save(candidate) : undefined}
                    onOpenLoan={setDrawerLoan} />
                );
              })}
            </div>
            <form className="ask-form" onSubmit={onSubmit}>
              <div className="prompt-chips" role="group" aria-label="Example questions">
                {words.prompts.map((p) => (
                  <button key={p} type="button" className="prompt-chip" disabled={busy} onClick={() => void ask(p)}>
                    {p}
                  </button>
                ))}
              </div>
              <div className="ask-input-row">
                <label htmlFor="ask-input" className="visually-hidden">Ask the tape</label>
                <textarea id="ask-input" ref={inputRef} rows={2} value={input} placeholder={words.placeholder}
                  onChange={(e) => setInput(e.target.value)} onKeyDown={onInputKey} />
                <button type="submit" className="send-btn" aria-label="Send question" disabled={busy || !input.trim()}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2"
                    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M5 12h14M13 6l6 6-6 6" />
                  </svg>
                </button>
              </div>
              <span className="muted small">{words.readOnlyNote}</span>
            </form>
          </section>
          <aside className="ask-side" aria-label="Agent workings">
            <SavedQueriesPanel saved={saved} onRerun={(q) => void rerun(q)} busy={busy} />
            <AgentToolsPanel />
          </aside>
        </div>
        {explainOpen && <ExplainPanel screen="ask-the-tape" onClose={() => setExplainOpen(false)} />}
      </div>

      {drawerLoan && <LoanDrawer loanId={drawerLoan} columns={columns} onClose={() => setDrawerLoan(null)} />}
    </div>
  );
}
