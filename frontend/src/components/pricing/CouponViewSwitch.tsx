/**
 * components/pricing/CouponViewSwitch.tsx: the "Traded coupons | All 25" switch on
 * the Price Grid (Step 6c).
 *
 * Where it sits: PriceGridScreen -> [CouponViewSwitch]; the choice drives both
 * PriceTable and PayupTable.
 *
 * BUSINESS: a desk mostly reads the coupons that trade today; the full 25 show how
 *   the model prices the deep discounts and premiums no one trades.
 * TECH: two toggle buttons (aria-pressed) in a labelled group. The screen owns the
 *   choice; this component only reports a click. Words from price-grid.json.
 */
import { fillCaption, priceGridContent } from "../../content/content";
import type { CouponView } from "../../pricing/priceGridView";

interface CouponViewSwitchProps {
  view: CouponView;
  /** How many coupons the grid has, for the "All {count}" label. */
  allCount: number;
  onChange: (view: CouponView) => void;
}

/**
 * The two-way switch.
 * BUSINESS: one choice for both tables, so the pay-ups line up with the prices.
 */
export function CouponViewSwitch({ view, allCount, onChange }: CouponViewSwitchProps) {
  const words = priceGridContent.view;
  const options: { id: CouponView; label: string }[] = [
    { id: "traded", label: words.traded },
    { id: "all", label: fillCaption(words.all, { count: allCount }) },
  ];
  return (
    <div className="view-switch" role="group" aria-label={words.label}>
      {options.map((o) => (
        <button key={o.id} type="button" className="view-switch-btn" aria-pressed={view === o.id}
          onClick={() => onChange(o.id)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}
