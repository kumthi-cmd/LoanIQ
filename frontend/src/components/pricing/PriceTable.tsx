/**
 * components/pricing/PriceTable.tsx: the Price Grid's TBA price table (Step 6c).
 *
 * Where it sits: PriceGridScreen -> [PriceTable]; rows from pricing/priceGridView.ts.
 *
 * BUSINESS: the desk's price file at a glance: coupons down the side, the six
 *   products across, and for each the Current price and the drop to next month, both
 *   in 32nds the way dealers quote them (98-08+ = 98.265625 points; a drop of 0-03+
 *   means next month trades 3.5/32 lower). Three things stand out:
 *   - the coupon nearest each product's current coupon is highlighted in the blue
 *     LoanIQ uses for "selected": the TBA trading closest to par;
 *   - model-only coupons (outside the traded band) are muted: priced, not traded;
 *   - a negative drop keeps its minus sign and no colour: a drop is carry, not P&L.
 * TECH:
 *   - A plain <table>, not AG Grid: about 150 cells with no paging or sort, and real
 *     <th scope> headers, so a screen reader reads "UMBS 30, Price, 6.0, 98-08+".
 *     The products header uses colSpan=2 over each Price and Drop pair.
 *   - Hovering a price shows its decimal (title); the decimal is the API's own
 *     string, never recomputed. Nearest and model-only are also written as hidden
 *     text, since a tint or a title alone is not read out.
 *   - Wide at 1440 px with the Explain panel open, so the table scrolls inside its
 *     card (.table-scroll) and never widens the page.
 */
import type { PriceGrid } from "../../api/types";
import { fillCaption, priceGridContent } from "../../content/content";
import { priceTableRows, type CouponView, type PriceTableCell } from "../../pricing/priceGridView";
import { GlossaryCaption } from "../GlossaryCaption";
import { CouponViewSwitch } from "./CouponViewSwitch";

interface PriceTableProps {
  grid: PriceGrid;
  view: CouponView;
  onViewChange: (view: CouponView) => void;
}

/**
 * The class names for one price or drop cell.
 * BUSINESS: nearest beats model-only; the nearest coupon is always traded anyway.
 * TECH: "pair-start" draws the line between one product's pair and the next.
 */
function cellClass(c: PriceTableCell, pairStart: boolean): string {
  return ["num", pairStart ? "pair-start" : "", c.nearest ? "nearest" : c.cell?.model_only ? "model-only" : ""]
    .filter(Boolean).join(" ");
}

/**
 * The hidden words a screen reader hears after a price.
 * BUSINESS: "nearest the current coupon" or "model-only", the same facts the tint shows.
 */
function cellNote(c: PriceTableCell): string {
  const words = priceGridContent.prices;
  if (c.nearest) return words.nearestTag;
  if (c.cell?.model_only) return words.modelTag;
  return "";
}

/**
 * The price table with its title row, view switch and legend.
 * BUSINESS: Current prices and drops for every product at the chosen coupons.
 * TECH: a missing cell (a product without that coupon) shows a dash.
 */
export function PriceTable({ grid, view, onViewChange }: PriceTableProps) {
  const words = priceGridContent.prices;
  const rows = priceTableRows(grid, view);
  return (
    <section className="price-card" aria-labelledby="price-table-title">
      <div className="price-card-head">
        <h3 id="price-table-title" className="panel-title">{words.title}</h3>
        <span className="muted small"><GlossaryCaption text={words.units} /></span>
        <CouponViewSwitch view={view} allCount={grid.coupons.length} onChange={onViewChange} />
      </div>
      <div className="table-scroll">
        <table className="price-table" aria-labelledby="price-table-title">
          <thead>
            <tr>
              <th scope="col" rowSpan={2} className="coupon-col">{words.coupon}</th>
              {grid.products.map((p) => (
                <th key={p.name} scope="colgroup" colSpan={2} className="pair-start product-col">{p.name}</th>
              ))}
            </tr>
            <tr>
              {grid.products.map((p) => [
                <th key={`${p.name}-price`} scope="col" className="num pair-start sub-col">{words.price}</th>,
                <th key={`${p.name}-drop`} scope="col" className="num sub-col">{words.drop}</th>,
              ])}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.coupon}>
                <th scope="row" className="coupon-col">{r.coupon}</th>
                {r.cells.map((c) => [
                  <td key={`${c.product}-price`} className={cellClass(c, true)}
                    title={c.cell ? fillCaption(words.priceTitle, { product: c.product, coupon: r.coupon, decimal: c.cell.price })
                      + (c.cell.model_only ? words.modelTag : "") : undefined}>
                    {c.cell?.price_32nds ?? "—"}
                    {c.cell && <span className="visually-hidden">{cellNote(c)}</span>}
                  </td>,
                  <td key={`${c.product}-drop`} className={cellClass(c, false)}
                    title={c.cell ? fillCaption(words.dropTitle, { product: c.product, coupon: r.coupon, decimal: c.cell.drop })
                      : undefined}>
                    {c.cell?.drop_text ?? "—"}
                  </td>,
                ])}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="price-legend">
        <span className="legend-item">
          <span className="legend-swatch" aria-hidden="true" /><GlossaryCaption text={words.legendNearest} />
        </span>
        <span><GlossaryCaption text={words.legendModel} /></span>
        <span>{words.legendDrop}</span>
        <span>{words.legendHover}</span>
      </div>
    </section>
  );
}
