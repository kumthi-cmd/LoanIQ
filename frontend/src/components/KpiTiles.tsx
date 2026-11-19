/**
 * components/KpiTiles.tsx: the tape's headline numbers above the grid.
 *
 * Where it sits: GET /api/loans/summary -> Loan Tape screen -> [KpiTiles].
 *
 * BUSINESS: the numbers a trader quotes first when describing a pool: how many
 *   loans, how much balance, the weighted-average coupon (WAC), credit (WA FICO),
 *   leverage (WA LTV) and how many loans are delinquent. WAC decides which agency
 *   coupons the pool can fit; FICO and LTV drive the price; delinquent loans
 *   usually cannot be pooled at all.
 * TECH: the averages are weighted by current UPB on the server
 *   (sum(value x current_upb) / sum(current_upb), backend/app/main.py). They cover
 *   the whole tape, not the grid's filter (decided in Step 1b); the caption says so.
 *   A null average (empty tape) shows as a dash. Each tile's label is a glossary
 *   term with its definition on hover.
 */
import type { Summary } from "../api/types";
import { formatNumber } from "../grid/columnFormats";
import { GlossaryTerm } from "./GlossaryTerm";

/** One tile: label, glossary term, and how to turn the summary into its value. */
interface Tile {
  label: string;
  term: string;
  value: (s: Summary) => string;
}

// TECH: shows "—" for a null average, else the formatted number with its unit.
const orDash = (v: number | null | undefined, text: (n: number) => string) =>
  v === null || v === undefined ? "—" : text(v);

/**
 * The six tiles, in the order a trader reads them.
 * BUSINESS: units on screen: dollars for UPB, percent for WAC and LTV, points for FICO.
 *   WA FICO shows whole points, the way FICO is quoted.
 */
export const TILES: Tile[] = [
  { label: "Loans", term: "Loan tape", value: (s) => formatNumber(s.loan_count, "count") },
  { label: "Current UPB", term: "UPB", value: (s) => `$${formatNumber(s.total_current_upb, "money")}` },
  { label: "WAC", term: "WAC", value: (s) => orDash(s.wac, (n) => `${formatNumber(n, "rate")}%`) },
  { label: "WA FICO", term: "Weighted average (WA)", value: (s) => orDash(s.wa_fico, (n) => formatNumber(n, "count")) },
  { label: "WA LTV", term: "LTV", value: (s) => orDash(s.wa_ltv, (n) => `${formatNumber(n, "ratio")}%`) },
  { label: "Delinquent loans", term: "MBA delinquency", value: (s) => formatNumber(s.delinquent_loans, "count") },
];

interface KpiTilesProps {
  /** The summary from the API; null while it loads. */
  summary: Summary | null;
}

/**
 * The KPI tile row.
 * BUSINESS: a pool's headline at a glance.
 * TECH: each tile is a <section> with an accessible name (aria-label), so tests and
 *   screen readers can find "WAC" and read its value. While loading, values show "…".
 */
export function KpiTiles({ summary }: KpiTilesProps) {
  return (
    <div className="kpi-row">
      <div className="kpi-tiles">
        {TILES.map((tile) => (
          <section key={tile.label} className="kpi-tile" aria-label={tile.label}>
            <div className="kpi-label">
              <GlossaryTerm term={tile.term}>{tile.label}</GlossaryTerm>
            </div>
            <div className="kpi-value">{summary ? tile.value(summary) : "…"}</div>
          </section>
        ))}
      </div>
      <p className="kpi-caption">Whole tape, weighted by current UPB. Synthetic, illustrative numbers.</p>
    </div>
  );
}
