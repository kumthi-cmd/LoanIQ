/**
 * components/ask/ToolChips.tsx: the tools the agent called for one answer, as chips.
 *
 * Where it sits: AnswerTurn -> [ToolChips]; data from the tool_call / tool_result
 * stream events (ask/conversation.ts).
 *
 * BUSINESS: "query_tape → 19 rows · summarize_tape · lookup_term: MBA delinquency".
 *   The visitor sees how the answer was reached, and clicking a chip shows the
 *   exact SQL that ran, so a trader can check the answer rather than trust it. A
 *   call the guardrails refused is marked, with the reason the model was given.
 * TECH: each chip is a toggle button (aria-expanded + aria-controls) for one detail
 *   box below the chips; only one is open at a time. Tools that run no SQL
 *   (lookup_term, list_columns, get_loan) show the input they were called with.
 */
import { useId, useState } from "react";
import type { ToolStep } from "../../ask/conversation";
import { formatNumber } from "../../grid/columnFormats";

/**
 * The chip's label.
 * BUSINESS: the count is rows MATCHED (total_rows), as the desk would quote it.
 */
export function chipLabel(step: ToolStep): string {
  const r = step.result;
  if (!r) return `${step.name} …`;
  if (r.status !== "ok") return `${step.name} ✕ ${r.status === "rejected" ? "refused" : "failed"}`;
  if (step.name === "query_tape" && typeof r.total_rows === "number") {
    return `query_tape → ${formatNumber(r.total_rows, "count")} ${r.total_rows === 1 ? "row" : "rows"}`;
  }
  if (step.name === "lookup_term" && typeof step.input.term === "string") return `lookup_term: ${step.input.term}`;
  if (step.name === "get_loan" && r.loan_id) return `get_loan: ${r.loan_id}`;
  return step.name;
}

/**
 * What the detail box shows: the SQL that ran, else the call's input.
 * TECH: a refused query_tape has no checked SQL, so the SQL the model wrote is shown.
 */
export function chipDetail(step: ToolStep): string {
  const sql = step.result?.sql ?? (typeof step.input.sql === "string" ? step.input.sql : undefined);
  if (sql) return sql;
  const entries = Object.entries(step.input);
  return entries.length ? entries.map(([k, v]) => `${k}: ${String(v)}`).join("\n") : "(no input)";
}

interface ToolChipsProps {
  steps: ToolStep[];
}

/**
 * The chips and the one open detail box.
 * TECH: useState holds the open step's index (null = none); useId links each chip to
 *   the box for screen readers.
 */
export function ToolChips({ steps }: ToolChipsProps) {
  const [open, setOpen] = useState<number | null>(null);
  const boxId = useId();
  if (steps.length === 0) return null;
  const step = open === null ? null : steps[open];
  return (
    <div className="tool-chips">
      <div className="tool-chip-row" role="group" aria-label="Tools the agent called">
        {steps.map((s, i) => (
          <button key={`${s.id}-${i}`} type="button"
            className={`tool-chip${s.result && s.result.status !== "ok" ? " tool-chip-refused" : ""}`}
            aria-expanded={open === i} aria-controls={boxId}
            onClick={() => setOpen((o) => (o === i ? null : i))}>
            {chipLabel(s)}
          </button>
        ))}
      </div>
      {step && (
        <div id={boxId} className="tool-detail" data-testid="tool-detail">
          <span className="eyebrow">{step.result?.sql || typeof step.input.sql === "string" ? "SQL" : "Input"} · {step.name}</span>
          <pre className="sql-block">{chipDetail(step)}</pre>
          {step.result?.reason && <span className="small tool-reason">{step.result.reason}</span>}
        </div>
      )}
    </div>
  );
}
