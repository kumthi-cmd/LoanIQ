/**
 * components/ColumnPicker.tsx: the "Columns" button that shows or hides grid fields.
 *
 * Where it sits: Loan Tape screen title row -> [ColumnPicker] -> LoanGrid (hidden columns).
 *
 * BUSINESS: a tape has ~41 fields; the grid opens on the dozen a trader reads first
 *   (gridConfig.ts). Anyone who needs servicer, CLTV, ARM caps or pay history ticks
 *   them here, and the grid shows them at once, without reloading any loans.
 * TECH: AG Grid's own column chooser (the Columns tool panel) is an Enterprise
 *   feature, so this is a small popover of checkboxes over the column list from
 *   /api/loans/columns. The button's aria-expanded / aria-controls tell a screen
 *   reader the list is open; Escape inside the list closes it and returns focus to
 *   the button. The pinned loan_id is always shown, so its box is checked and
 *   disabled. The picker does not own the state: the screen holds the hidden set and
 *   passes the change back up (a "controlled" component).
 */
import { useId, useRef, useState, type KeyboardEvent } from "react";
import type { ColumnInfo } from "../api/types";
import { PINNED_COLUMN } from "../grid/loanColumns";

interface ColumnPickerProps {
  /** Every tape column, in tape order. */
  columns: ColumnInfo[];
  /** Names currently hidden. */
  hidden: ReadonlySet<string>;
  /** Called with the new hidden set when a box is ticked or cleared. */
  onChange: (hidden: Set<string>) => void;
}

/**
 * The Columns button and its list.
 * BUSINESS: choose which tape fields the grid shows.
 * TECH: useRef (a React hook) keeps a handle on the button, so focus can return to it.
 */
export function ColumnPicker({ columns, hidden, onChange }: ColumnPickerProps) {
  const [open, setOpen] = useState(false);
  const listId = useId();
  const buttonRef = useRef<HTMLButtonElement>(null);

  // TECH: a new Set each time, never a change to the old one, so React sees new state.
  const toggle = (name: string) => {
    const next = new Set(hidden);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    onChange(next);
  };

  const closeOnEscape = (e: KeyboardEvent) => {
    if (e.key === "Escape") {
      setOpen(false);
      buttonRef.current?.focus();
    }
  };

  const shown = columns.length - columns.filter((c) => hidden.has(c.name) && c.name !== PINNED_COLUMN).length;
  return (
    <div className="column-picker">
      <button ref={buttonRef} type="button" className="btn" aria-expanded={open} aria-controls={listId}
        onClick={() => setOpen((o) => !o)}>
        Columns <span className="muted">{shown}/{columns.length}</span>
      </button>
      {open && (
        <fieldset id={listId} className="column-list" onKeyDown={closeOnEscape}>
          <legend className="visually-hidden">Grid columns</legend>
          {columns.map((c) => (
            <label key={c.name}>
              <input type="checkbox" checked={c.name === PINNED_COLUMN || !hidden.has(c.name)}
                disabled={c.name === PINNED_COLUMN} onChange={() => toggle(c.name)} />
              {c.label}
            </label>
          ))}
        </fieldset>
      )}
    </div>
  );
}
