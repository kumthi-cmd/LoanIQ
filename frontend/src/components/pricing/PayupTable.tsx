/**
 * components/pricing/PayupTable.tsx: the Price Grid's spec pay-up table (Step 6c).
 *
 * Where it sits: PriceGridScreen -> [PayupTable]; rows from GET /api/prices/grid
 * "payups", columns from pricing/priceGridView.ts.
 *
 * BUSINESS: what each spec story (low loan balance tiers, New York, Puerto Rico, low
 *   FICO) is worth over TBA on one product, at each coupon, in 32nds. Read across a
 *   row and the S-curve shows: 0 on discount coupons (no one can refinance, so slow
 *   prepayment is worth nothing), rising near the current coupon, the full pay-up on
 *   premium coupons. LLB 85K on UMBS 30 at 6.0: 18+ (18.5/32 of a point). Best
 *   execution (Step 6d) adds these to the TBA prices above.
 * TECH:
 *   - One product at a time, picked with toggle chips (aria-pressed), so the table
 *     stays readable; the six products' rows differ only through their current
 *     coupons. The screen owns the choice and the coupon view.
 *   - "Traded coupons" shows the product's own traded band (its cells that are not
 *     model_only); "All 25" shows every coupon, model-only ones muted.
 *   - A zero is muted, so the eye goes to where the stories are worth something.
 *     The nearest coupon's column is tinted, as in the price table.
 *   - Values are the API's, rounded to half a 32nd on the back end, shown as "18+".
 */
import type { PriceGrid } from "../../api/types";
import { fillCaption, priceGridContent } from "../../content/content";
import {
  formatPayup32nds, nearestCoupon, payupRowsFor, productTradedCoupons, type CouponView,
} from "../../pricing/priceGridView";
import { captionText, GlossaryCaption } from "../GlossaryCaption";

interface PayupTableProps {
  grid: PriceGrid;
  view: CouponView;
  /** The product shown, by name ("UMBS 30"). */
  product: string;
  onProductChange: (product: string) => void;
}

/**
 * The pay-up table with its product chips and range caption.
 * BUSINESS: every story's pay-up on the chosen product, at the chosen coupons.
 * TECH: a coupon a story row lacks shows a dash. If the chosen product is not in the
 *   grid, the first product is shown instead.
 */
export function PayupTable({ grid, view, product, onProductChange }: PayupTableProps) {
  const words = priceGridContent.payups;
  const row = grid.products.find((p) => p.name === product) ?? grid.products[0];
  if (!row) return null;
  const traded = new Set(productTradedCoupons(row));
  const coupons = view === "traded" ? grid.coupons.filter((c) => traded.has(c)) : grid.coupons;
  const nearest = nearestCoupon(grid.coupons, row.current_coupon_pct);
  const stories = payupRowsFor(grid, row.name);
  const range = view === "traded" && coupons.length > 0
    ? fillCaption(words.rangeTraded, { product: row.name, low: coupons[0], high: coupons[coupons.length - 1] })
    : fillCaption(words.rangeAll, { product: row.name, count: coupons.length });
  // TECH: a coupon's column class: tinted if nearest, muted if model-only here.
  const colClass = (c: string) => (c === nearest ? "nearest" : traded.has(c) ? "" : "model-only");

  return (
    <section className="price-card" aria-label={captionText(words.title)}>
      <div className="price-card-head">
        <h3 className="panel-title"><GlossaryCaption text={words.title} /></h3>
        <span className="muted small">{words.units} · {range}</span>
        <div className="payup-chips" role="group" aria-label={words.productLabel}>
          {grid.products.map((p) => (
            <button key={p.name} type="button" className="chip" aria-pressed={p.name === row.name}
              onClick={() => onProductChange(p.name)}>
              {p.name}
            </button>
          ))}
        </div>
      </div>
      <div className="table-scroll">
        {/* TECH: named in plain words (captionText): the heading's glossary term would
            add its hidden definition to the name. */}
        <table className="price-table payup-table" aria-label={`${captionText(words.title)} · ${row.name}`}>
          <thead>
            <tr>
              <th scope="col" className="story-col">{words.story}</th>
              <th scope="col" className="num">{words.full}</th>
              {coupons.map((c) => <th key={c} scope="col" className={`num ${colClass(c)}`}>{c}</th>)}
            </tr>
          </thead>
          <tbody>
            {stories.map((s) => {
              const byCoupon = new Map(s.cells.map((cell) => [cell.coupon, cell.payup_32nds]));
              return (
                <tr key={s.story}>
                  <th scope="row" className="story-col">{s.story_label}</th>
                  <td className="num muted">{formatPayup32nds(s.full_32nds)}</td>
                  {coupons.map((c) => {
                    const v = byCoupon.get(c);
                    const zero = v !== undefined && Number(v) === 0;
                    return (
                      <td key={c} className={`num ${colClass(c) || (zero ? "zero" : "")}`}>
                        {v === undefined ? "—" : formatPayup32nds(v)}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="price-note">{words.note}</p>
    </section>
  );
}
