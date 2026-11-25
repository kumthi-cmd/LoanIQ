# Public sources
Every business rule in LoanIQ traces to a public source. Add a row when you add a rule.

| Topic | Public source | Used for |
| --- | --- | --- |
| Conforming loan limits | FHFA conforming loan limit announcements (fhfa.gov) | Jumbo and high-balance flags; yearly baseline limits and 150% high-cost ceiling in the tape generator |
| Delinquency status | Mortgage Bankers Association (MBA) delinquency method | dq_status buckets; status order of the Loan Tape's delinquency panel; the "90+ / FC / REO / BK" desk question (`desk_questions.toml`) |
| Delinquency drivers and level | Fannie Mae Single-Family Loan Performance Data; MBA National Delinquency Survey | Direction of the tape's risk score (FICO, DTI, LTV, investor, cash-out) and a plausible overall rate. Coefficients and the 7% target are illustrative |
| Mortgage rates by month, 2015-2025 | FHFA National Mortgage Database (NMDB) aggregate statistics, new mortgage statistics, monthly, national, Conventional Conforming Market, `AVE_INTRATE` (average contract rate at origination), VALUE1. https://www.fhfa.gov/data/national-mortgage-database-aggregate-statistics | Base note rate for each origination month (`base_rate_30y_by_month`). Averages all terms, mostly 30-year; approximate |
| Mortgage rates, 2026 | MBA Weekly Applications Survey press releases, 30-year fixed conforming contract rate: 2026-01-21 (6.16%), 2026-04-15 (6.42%), 2026-07-15 (6.65%), 2026-10-14 (7.50%), at https://www.mba.org/news-and-research/newsroom | 2026 base rates, straight-line between those four readings; approximate and illustrative. NMDB had no 2026 data when this was written |
| Credit add-ons to rate | Fannie Mae Loan-Level Price Adjustment (LLPA) Matrix | Shape of the FICO, LTV, occupancy and cash-out add-ons, expressed as rate. Sizes are illustrative |
| Home price changes | FHFA House Price Index (fhfa.gov/hpi) | Annual change used to move appraised value to current value. 2025-2026 are illustrative estimates |
| FHA limits | HUD Handbook 4000.1 | FHA 96.5% maximum purchase LTV, 80% cash-out, primary residence only |
| VA limits | VA Lenders Handbook (VA Pamphlet 26-7) | VA up to 100% LTV, primary residence only |
| USDA limits | USDA Rural Development Handbook HB-1-3555 | USDA up to 100% LTV, 30-year fixed, purchase and rate/term only |
| Conventional eligibility | Fannie Mae Eligibility Matrix | Conventional LTV caps by purpose and occupancy; 50% DTI maximum |
| High-LTV refinance | FHFA Home Affordable Refinance Program (HARP) and High LTV Refinance Option | Loans with original LTV above 125, 2015-2018; the "LTV over 125" desk question |
| SOFR ARMs | Fannie Mae SOFR ARM plan descriptions | 5/6, 7/6 and 10/6 ARMs from 2021, 30-day average SOFR index, 2/1/5 and 5/1/5 caps |
| Low-loan-balance tiers | Fannie Mae, "Specified Pay-ups in Pricing & Execution - Whole Loan" (March 2018), https://singlefamily.fanniemae.com/media/5056/display | LLB tiers $85K, $110K, $150K, $175K. Tiers in use: `backend/app/config/spec_stories.toml` |
| Balance bands, Puerto Rico and FICO stories | Markit, "Agency RMBS - Specified Pool Summary" (May 2016), https://cdn.ihs.com/www/blog/commentary/pdf/Markit-Agency-RMBS--Specified-Pool-Summary--May-2016.pdf | Balance bands from 85K to 175K (85K, 110K, 125K, 150K, 175K); "PR Geo" story (also the "Puerto Rico" desk question); "Low FICO" story defined as FICO below 700 |
| Higher LLB tiers | Fannie Mae, "Low Balance Lending Economics: The Role of the Spec Pay-up" (December 2023), https://fanniemae.com/media/49786/display | $250K maximum balance widely traded; $275K newer. The $200K and $225K tiers are illustrative steps between published tiers |
| New York story | MCT, "MBS Pool Optimization 101", https://mct-trading.com/mbs-pool-optimization/ | New York as a state spec story; such loans are less likely to pay off early. Also the "New York" desk question |
| Agency loan eligibility | Fannie Mae Selling Guide | Slotting rules (Step 5a, `backend/app/config/slotting.toml`): Conventional and High-Balance loans go into UMBS; agency pools take current loans only; the 25 bps minimum servicing fee inside the coupon strip. Illustrative |
| TBA trading and good delivery | SIFMA Uniform Practices for mortgage-backed securities | Slotting (Step 5a, `slotting.toml`): only 30-, 20- and 15-year fixed-rate loans trade as TBA coupons, so ARMs and interest-only loans are not slotted; half-point coupon steps; settlement (Step 6) |

## Rules without a recorded source
These rules are in use but no public source is recorded for them yet. Each is labelled
illustrative in config and on screen.

| Rule | Where | Note |
| --- | --- | --- |
| FHA, VA and USDA loans go into GNMA II pools | `slotting.toml` `[agencies]` | Industry practice; no public source recorded |
| Non-QM loans have no agency pool | `slotting.toml` `[agencies]` `none` | Jumbo is covered by the FHFA conforming loan limits above; Non-QM is not |
| One 0.50 minimum strip for every agency | `slotting.toml` `[coupons]` `min_strip_pct` | Only the 25 bps servicing part is sourced (Fannie Mae Selling Guide); real minimums differ by agency and deal |
