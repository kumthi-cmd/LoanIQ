/**
 * screens/PriceGridScreen.tsx: the Price Grid screen (route "/prices", Step 6c).
 *
 * Where it sits: the third step of the desk's flow:
 *   loan tape -> slotting -> [price file] -> best execution -> positions and optimizer
 *   GET /api/prices/grid (backend/app/pricing/, Steps 6a and 6b) -> [this screen]
 *
 * BUSINESS: the desk's price file, top to bottom:
 *   1. the title line with "Illustrative, as of ..." (every price is illustrative);
 *   2. the strip: trade date, Treasury curve date and freshness, source, data links;
 *   3. six product cards: current coupon, its anchor, the SIFMA Current month and roll;
 *   4. the TBA price table: price and drop at each coupon, nearest coupon tinted;
 *   5. the spec pay-up table for one product.
 *   The "Explain this screen" button opens the explanation and the 13 terms the
 *   screen depends on. It starts closed, as on the Loan Tape, so the tables get the
 *   full width.
 * TECH:
 *   - One API call when the screen appears (useEffect), cancelled with an
 *     AbortController if the visitor leaves first. The first call of a New York day
 *     can wait a few seconds for Treasury, so a loading line shows meanwhile.
 *   - A failure, including the 503 the back end sends when no price file can be
 *     built (SIFMA's dates run out), shows one alert with the server's message.
 *   - The screen owns the UI state both tables share: the coupon view (traded or
 *     all) and the pay-up product, plus whether the explanation is open.
 *   - The header's loan count belongs to screens with a loan grid; this one clears
 *     it through the layout's outlet context.
 *   - Layout as on the Loan Tape: the tables and the Explain panel side by side,
 *     wrapping below each other at narrow widths (styles.css .screen-body).
 */
import { useEffect, useState } from "react";
import { useOutletContext } from "react-router";
import { fetchPriceGrid } from "../api/client";
import type { PriceGrid } from "../api/types";
import { ExplainPanel } from "../components/ExplainPanel";
import { PayupTable } from "../components/pricing/PayupTable";
import { PriceFileStrip } from "../components/pricing/PriceFileStrip";
import { PriceTable } from "../components/pricing/PriceTable";
import { ProductCard } from "../components/pricing/ProductCard";
import { fillCaption, priceGridContent } from "../content/content";
import type { CouponView } from "../pricing/priceGridView";
import type { LayoutContext } from "../App";

/**
 * The Price Grid screen.
 * BUSINESS: today's illustrative TBA prices, drops and pay-ups for six products.
 * TECH: setRowCount from the layout is stable, so the effect runs once.
 */
export function PriceGridScreen() {
  const { setRowCount } = useOutletContext<LayoutContext>();
  const [grid, setGrid] = useState<PriceGrid | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<CouponView>("traded");
  // BUSINESS: the pay-up table opens on the first product (UMBS 30, the most traded).
  const [payProduct, setPayProduct] = useState<string | null>(null);
  const [explainOpen, setExplainOpen] = useState(false);

  useEffect(() => {
    // TECH: no loan grid here, so the header shows no loan count.
    setRowCount(null);
    const ctrl = new AbortController();
    fetchPriceGrid(ctrl.signal)
      .then(setGrid)
      .catch((e: Error) => {
        if (!ctrl.signal.aborted) setError(e.message);
      });
    return () => ctrl.abort();
  }, [setRowCount]);

  const words = priceGridContent;
  return (
    <div className="screen">
      <div className="screen-title-row">
        <div className="screen-title">
          <span className="eyebrow">{words.eyebrow}</span>
          <h2>Price Grid</h2>
        </div>
        {grid && <span className="illustrative-pill">{grid.label}</span>}
        <div className="title-actions">
          <button type="button" className="btn btn-accent" aria-expanded={explainOpen}
            onClick={() => setExplainOpen((o) => !o)}>
            {explainOpen ? "Hide explanation" : "Explain this screen"}
          </button>
        </div>
      </div>

      {error && (
        <div role="alert" className="grid-error">
          {fillCaption(words.error, { message: error })}
        </div>
      )}
      {!grid && !error && <p role="status" className="muted">{words.loading}</p>}

      <div className="screen-body">
        {grid && (
          <div className="screen-main">
            <PriceFileStrip grid={grid} />
            <section className="product-cards" aria-label="Products">
              {grid.products.map((p) => <ProductCard key={p.name} product={p} />)}
            </section>
            <PriceTable grid={grid} view={view} onViewChange={setView} />
            <PayupTable grid={grid} view={view} product={payProduct ?? grid.products[0]?.name ?? ""}
              onProductChange={setPayProduct} />
          </div>
        )}
        {explainOpen && <ExplainPanel screen="price-grid" onClose={() => setExplainOpen(false)} />}
      </div>
    </div>
  );
}
