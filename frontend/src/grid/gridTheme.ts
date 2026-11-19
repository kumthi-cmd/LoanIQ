/**
 * grid/gridTheme.ts: the dark, dense look of every LoanIQ grid.
 *
 * BUSINESS: a trading-desk grid, with a dark background for long sessions and rows
 *   about 30 px tall so one screen shows many loans. Headers are small, muted and
 *   upper-case so the eye goes to the numbers; rows are separated by thin lines, not
 *   stripes, and the row under the mouse is lit so a trader can follow it across.
 * TECH: AG Grid's Theming API. Start from the Quartz theme, apply its dark blue
 *   color scheme with withPart(), then set colors and sizes with withParams().
 *   The colors match the tokens in styles.css (and the LoanIQ design canvas) so the
 *   grid and the page look like one app. Upper-case headers and tabular numerals
 *   (digits of equal width, so columns of numbers line up) are set in styles.css,
 *   because the theme has no parameter for them.
 */
import { colorSchemeDarkBlue, themeQuartz } from "ag-grid-community";

export const loanIqGridTheme = themeQuartz.withPart(colorSchemeDarkBlue).withParams({
  backgroundColor: "#0f1724",
  oddRowBackgroundColor: "#0f1724",
  foregroundColor: "#d7dee9",
  accentColor: "#4c9aff",
  borderColor: "#22304a",
  rowBorder: { color: "#1a263b" },
  rowHoverColor: "#132036",
  headerBackgroundColor: "#152033",
  headerTextColor: "#8a97ab",
  headerFontWeight: 500,
  fontFamily: "Inter, 'Segoe UI', system-ui, sans-serif",
  fontSize: 12.5,
  headerFontSize: 11,
  rowHeight: 30,
  headerHeight: 34,
  spacing: 4,
  wrapperBorderRadius: 0,
});
