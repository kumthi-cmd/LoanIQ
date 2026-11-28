## Business
This is the desk's price file: what each agency TBA product is worth today, at every
coupon. Best execution starts here. A loan is worth the price of the pool it goes
into, plus any pay-up its spec story earns, so a desk reads this screen before it
decides where each loan goes.

Each card is one product (UMBS 30, 20 and 15, and GNMA II 30, 20 and 15). The
**current coupon** is the coupon that would trade at par today. It moves with
Treasury yields every day, so the whole grid moves with it. The card also shows the
product's **Current** delivery month from SIFMA's calendar. Current rolls to the next
month the day after the 48-hour notification date, and the three SIFMA classes roll
on different days.

The table has a price and a **drop** for every coupon. Prices are in points and 32nds,
the way every dealer quotes them. The drop is how much cheaper next month trades: one
month of coupon, less the cost of financing the bonds until next month's settlement,
plus principal prepaid at par. A seller compares it with the cost of waiting to
decide whether to deliver now or roll. When financing costs more than a low coupon
earns, the drop turns negative. The coupon nearest the current coupon is highlighted.
Coupons outside the traded band are model-only: the model prices them, but no one
would trade them today.

The pay-up table shows what each spec story is worth over TBA at each coupon. On a
discount coupon no one can refinance, so slow prepayment is worth nothing; on a premium
coupon the full pay-up applies. In between it follows an S-curve. Every price, drop and
pay-up is illustrative, built from public data only.

## Technical
The screen makes one call, `GET /api/prices/grid`, and draws everything from that
answer. The back end builds the file in `backend/app/pricing/`. Each product's current
coupon is Treasury's daily par yield at its anchor tenor plus a spread. Prices come
from a straight line below the current coupon and a curve that flattens toward a
prepayment cap above it. SIFMA's dates pick the Current month, and the drop is worked
from the 1-month bill yield and a prepayment speed. All of it is in Decimal and rounded
to half a 32nd only at the end. Every setting lives in
`backend/app/config/pricing.toml`, and the sources are in `docs/public-sources.md`.

The tables are plain HTML tables, not AG Grid. There are about 150 cells, with no paging
or server sort, and a real table gives screen readers its row and column headers. The
screen never rounds or recomputes a price. Numbers arrive as Decimal strings and are
shown as sent. The one thing it works out is which coupon is nearest the current
coupon, to highlight it. Which coupons trade comes from the back end's `model_only`
flag, so the traded band is defined once, in the config.

The header strip says how fresh the curve is: **Live** (fetched today), **Cached**
(Treasury could not be reached, so the last curve is kept) or **Sample curve** (the
bundled fixture). If no price file can be built, for example once SIFMA's dates run
out, the API answers 503 and the screen shows its message instead of stale numbers.
The types come from the back end's OpenAPI spec, so a change to the API breaks the
build, not the screen.
