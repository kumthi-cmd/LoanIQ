/**
 * grid/gridTheme.ts: the dark, dense look of every LoanIQ grid.
 *
 * BUSINESS: a trading-desk grid, with a dark background for long sessions and rows
 *   about 28 px tall so one screen shows many loans.
 * TECH: AG Grid's Theming API. Start from the Quartz theme, apply its dark blue
 *   color scheme with withPart(), then set colors and sizes with withParams().
 *   The colors match the tokens in styles.css so the grid and the page look like
 *   one app. Tabular numerals (digits of equal width, so columns of numbers line
 *   up) are switched on in styles.css.
 */
import { colorSchemeDarkBlue, themeQuartz } from "ag-grid-community";

export const loanIqGridTheme = themeQuartz.withPart(colorSchemeDarkBlue).withParams({
  backgroundColor: "#0f1724",
  oddRowBackgroundColor: "#121c2b",
  foregroundColor: "#d7dee9",
  accentColor: "#4c9aff",
  fontFamily: "Inter, 'Segoe UI', system-ui, sans-serif",
  fontSize: 12,
  headerFontSize: 12,
  rowHeight: 28,
  headerHeight: 32,
  spacing: 4,
});
