/**
 * components/pricing/PriceFileStrip.tsx: the line under the Price Grid's title that
 * says what the prices are for and how fresh they are (Step 6c).
 *
 * Where it sits: PriceGridScreen -> [PriceFileStrip]; data from GET /api/prices/grid.
 *
 * BUSINESS: before reading a price, a trader checks three things: which trade date
 *   the file is for (it picks the Current month), which Treasury curve it was built
 *   from and whether that curve is today's, and who made the prices. A stale curve
 *   (Treasury down, or the bundled sample) is flagged in amber, the colour LoanIQ
 *   keeps for warnings; a live curve is green. The data sources link to the public
 *   pages behind the numbers.
 * TECH: words from content/screens/price-grid.json; source names with a url come
 *   from the API's sources list (content/pricing.json on the back end), so neither
 *   is repeated here. LoanIQ's own model has no url and is named by price_source.
 */
import type { PriceGrid } from "../../api/types";
import { priceGridContent } from "../../content/content";
import { longDate } from "../../pricing/priceGridView";

interface PriceFileStripProps {
  grid: PriceGrid;
}

/**
 * The trade date, curve date and status, source and data links.
 * BUSINESS: "Trade date Fri 27 Nov 2026 · Treasury curve Fri 27 Nov 2026 (Live) ·
 *   Source LoanIQ illustrative model · Data: U.S. Treasury..., SIFMA...".
 * TECH: the status pill's class names the status (status-live, status-cached,
 *   status-fixture); styles.css gives live the "ok" colours and the other two the
 *   warning colours. An unknown price_source is shown as sent.
 */
export function PriceFileStrip({ grid }: PriceFileStripProps) {
  const { strip, status, sourceNames } = priceGridContent;
  const sourceName = (sourceNames as Record<string, string>)[grid.price_source] ?? grid.price_source;
  const links = grid.sources.filter((s) => s.url);
  return (
    <div className="price-strip" aria-label="Price file">
      <span>
        <span className="muted">{strip.tradeDate}</span> {longDate(grid.trade_date)}
      </span>
      <span>
        <span className="muted">{strip.curve}</span> {longDate(grid.as_of)}{" "}
        <span className={`status-pill status-${grid.curve_status}`}>
          <span className="status-dot" aria-hidden="true" />
          {status[grid.curve_status]}
        </span>
      </span>
      <span>
        <span className="muted">{strip.source}</span> {sourceName}
      </span>
      {links.length > 0 && (
        <span className="price-strip-links muted">
          {strip.data}{" "}
          {links.map((s, i) => (
            <span key={s.name}>
              {i > 0 && " · "}
              <a href={s.url ?? undefined} target="_blank" rel="noreferrer">{s.name}</a>
            </span>
          ))}
        </span>
      )}
    </div>
  );
}
