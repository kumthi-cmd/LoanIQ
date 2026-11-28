/**
 * components/pricing/ProductCard.tsx: one product's card on the Price Grid (Step 6c).
 *
 * Where it sits: PriceGridScreen -> [ProductCard] x 6; data from GET /api/prices/grid.
 *
 * BUSINESS: what a trader needs about a product before reading its prices:
 *   - the current coupon (the coupon that trades at par today) and where it comes
 *     from: Treasury's par yield at the anchor tenor plus a spread
 *     (UMBS 30: 10Y 4.940 + 1.350 = 6.290%);
 *   - the Current delivery month and its SIFMA class, notification and settlement
 *     dates: when Current rolls, and when the bonds are delivered;
 *   - the month it rolls to, the days between settlements and the financing rate:
 *     the inputs to the drop.
 * TECH: every number comes from the API as sent; rates are padded to three decimals
 *   (rate3) and dates shortened (shortDate). Words from content/screens/price-grid.json.
 *   An <article> labelled by the product name, so a screen reader can jump between
 *   the six cards.
 */
import type { ProductRow } from "../../api/types";
import { fillCaption, priceGridContent } from "../../content/content";
import { rate3, shortDate } from "../../pricing/priceGridView";
import { GlossaryTerm } from "../GlossaryTerm";

interface ProductCardProps {
  product: ProductRow;
}

/**
 * One product card.
 * BUSINESS: current coupon, its anchor, and the Current month's SIFMA roll.
 * TECH: reads the first month (Current); a product with no months shows only its
 *   current coupon, rather than crashing.
 */
export function ProductCard({ product }: ProductCardProps) {
  const { card } = priceGridContent;
  const month = product.months[0];
  const headingId = `product-${product.name.replace(/\W+/g, "-").toLowerCase()}`;
  return (
    <article className="product-card" aria-labelledby={headingId}>
      <div className="product-card-head">
        <h3 id={headingId} className="product-card-name">{product.name}</h3>
        {month && (
          <span className="muted small">
            <GlossaryTerm term="SIFMA class">{fillCaption(card.sifmaClass, { cls: month.sifma_class })}</GlossaryTerm>
          </span>
        )}
      </div>
      <div className="product-card-cc">
        <span className="muted small"><GlossaryTerm term="Current coupon">{card.currentCoupon}</GlossaryTerm></span>
        <span className="product-card-cc-value">{rate3(product.current_coupon_pct)}%</span>
        <span className="muted small">
          {fillCaption(card.anchor, {
            tenor: product.anchor_tenor, yield: rate3(product.anchor_yield_pct), spread: rate3(product.spread_pct),
          })}
        </span>
      </div>
      {month && (
        <div className="product-card-roll">
          <span>
            <GlossaryTerm term="Current month">{card.current}</GlossaryTerm>{" "}
            <strong className="product-card-month">{month.label}</strong>
          </span>
          {/* TECH: two halves that never break inside ("Settle 10 Dec" stays whole), so
              a narrow card wraps at the dot, not between a day and its month. */}
          <span className="muted">
            <span className="nowrap">{fillCaption(card.notify, { notification: shortDate(month.notification_date) })}</span>
            {" · "}
            <span className="nowrap">{fillCaption(card.settle, { settlement: shortDate(month.settlement_date) })}</span>
          </span>
          <span className="muted">{fillCaption(card.roll, { next: month.next_label, days: month.days })}</span>
          <span className="muted">{fillCaption(card.financing, { rate: rate3(month.financing_rate_pct) })}</span>
        </div>
      )}
    </article>
  );
}
