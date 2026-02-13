# APEX2 Prepayment Model Review

## Overview

APEX2 represents a significant step forward from PPD_OLD, which had no analytical
pricing layer at all. APEX2 introduced data-driven prepayment estimation, ROE-based
pricing, and dimensional analysis across 8 loan characteristics. This review
identifies areas where the next-generation engine can build on that foundation.

## Architecture Summary

APEX2 computes a **payment speed multiplier** (actual payments / expected payments)
for each loan by looking up the loan's characteristics in 8 dimensional tables,
then averaging the results equally. This multiplier feeds into an amortization
calculation that determines effective loan life, which drives present value and
pricing.

## Opportunities for Improvement

### 1. Dimension Weighting

APEX2 averages all 8 dimensions with equal weight. In practice, some dimensions
(credit score, rate delta) are likely more predictive of prepayment than others
(collateral state, ATR method). A weighted or regression-based combination could
improve accuracy — dimensions with more predictive power and larger sample sizes
should carry more influence.

### 2. Correlated Dimensions

Interest rate (`interestRateBand`) and rate delta (`interestRateDeltaBand`) are
both included as separate dimensions, but rate delta = rate - treasury, making
them highly correlated. The equal-weight average effectively gives interest rate
~25% of the total signal (2 of 8 dimensions). A combined model could handle
this more cleanly.

### 3. Seasoning / Loan Age

APEX2 does not adjust for loan age. Industry models (PSA, agency prepayment
curves) consistently show that new loans prepay at lower rates than seasoned
loans — borrowers rarely refinance within the first 1-2 years. Adding a
seasoning component could improve accuracy, especially when pricing packages
with a mix of new and seasoned loans.

### 4. Time-Varying Rate Environment

The `prepaymentRateOverAll` metric aggregates actual-vs-expected ratios across
the full loan history (back to 2007+). This blends very different interest rate
regimes: the post-crisis period, ZIRP (2009-2015), the 2020-2021 refi boom, and
the 2022+ rate shock. Prepayment behavior in a 3% rate environment is
fundamentally different from a 7% environment. A time-weighted or
regime-segmented approach could better reflect current conditions.

### 5. Sample Size Variation Across Bands

Some dimensional bands are backed by large loan populations (e.g., SFOO
collateral, 1st lien position), while others may have very few observations
(e.g., "Accounts receivable" collateral at 24.28x, "Equipment and Other
Collateral" at 0.0x). The equal-weight average doesn't account for statistical
confidence — a thin band gets the same influence as a thick one. Adding minimum
observation thresholds or confidence weighting would make the model more robust.

### 6. Internal vs. Market Data

APEX2's dimensional rates are calibrated from the internal loan portfolio. For
ITIN lending, this is a strong dataset — likely one of the best in the industry.
For non-ITIN loans, the internal sample represents a fraction of the broader
non-QM market. Since most acquired packages are non-ITIN, the prepayment
estimates for these loans could benefit from supplemental market data or
post-acquisition performance tracking to validate and refine the rates.

### 7. Monthly Term Structure

APEX2 produces a single flat prepayment multiplier per loan, which is then used
to compute a single effective life (the "amortization plug"). In reality,
prepayment behavior varies over the life of a loan — low early, ramping up,
potentially declining again as the remaining population becomes less mobile.
A month-by-month hazard model could capture this term structure and produce
more accurate cash flow projections, especially for discount purchases where
the timing of prepayment significantly affects ROE.

### 8. Interaction Effects

The dimensional approach treats each characteristic independently. In practice,
a high-credit, low-LTV borrower with a rate 3% above market has compounding
reasons to prepay — these effects multiply rather than add. A model that
captures interactions (even simple two-way interactions between credit and rate
delta) could better identify loans at the tails of the prepayment distribution.

## What APEX2 Gets Right

- **Data-driven**: Grounded in actual loan performance, not assumptions
- **Multi-dimensional**: Considers 8 distinct loan characteristics
- **ITIN stratification**: Recognizes fundamentally different behavior patterns
- **Integration with pricing**: Flows directly into ROE-based bid pricing
- **Transparent**: Simple enough that analysts can understand and explain results
- **The ITIN dataset**: Likely best-in-class for this borrower segment

## Recommendations for the New Engine

1. **Preserve the dimensional insight** — the 8 dimensions APEX2 identified are
   the right features to consider; the improvement is in how they're combined
2. **Add seasoning and term structure** — month-by-month projection instead of
   a single flat multiplier
3. **Weight dimensions by predictive power** — regression or ML to learn optimal
   combination weights
4. **Build a post-acquisition performance feedback loop** — track how actual
   runoff compares to predicted, especially for non-ITIN packages
5. **Separate ITIN and non-ITIN model paths** — the data quality is different,
   the calibration sources should be different
6. **Consider recency weighting** — more recent performance data should carry
   more weight than 2007-era observations
