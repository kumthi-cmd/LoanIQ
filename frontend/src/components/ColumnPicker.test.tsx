/**
 * Tests for components/ColumnPicker.tsx.
 * BUSINESS: a trader can show any hidden tape field and hide any shown one, except
 *   the loan ID, which always stays so a row can be identified.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ColumnPicker } from "./ColumnPicker";

const COLUMNS = [
  { name: "loan_id", type: "VARCHAR", kind: "text", label: "Loan ID", default_visible: false },
  { name: "state", type: "VARCHAR", kind: "text", label: "State", default_visible: false },
  { name: "servicer", type: "VARCHAR", kind: "text", label: "Servicer", default_visible: false },
];

describe("ColumnPicker", () => {
  it("opens a list with each column ticked if shown", async () => {
    render(<ColumnPicker columns={COLUMNS} hidden={new Set(["servicer"])} onChange={vi.fn()} />);
    const button = screen.getByRole("button", { name: /Columns/ });
    expect(button).toHaveTextContent("2/3");
    expect(button).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("checkbox", { name: "State" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Servicer" })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Loan ID" })).toBeDisabled();
  });

  it("reports the new hidden set when a box changes", async () => {
    const onChange = vi.fn();
    render(<ColumnPicker columns={COLUMNS} hidden={new Set(["servicer"])} onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: /Columns/ }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Servicer" }));
    expect([...onChange.mock.calls[0][0]]).toEqual([]);
    await userEvent.click(screen.getByRole("checkbox", { name: "State" }));
    expect([...onChange.mock.calls[1][0]].sort()).toEqual(["servicer", "state"]);
  });

  it("closes on Escape and gives focus back to the button", async () => {
    render(<ColumnPicker columns={COLUMNS} hidden={new Set()} onChange={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: /Columns/ }));
    screen.getByRole("checkbox", { name: "State" }).focus();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("checkbox", { name: "State" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Columns/ })).toHaveFocus();
  });
});
