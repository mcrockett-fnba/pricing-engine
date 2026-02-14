# Pricing Engine TODO

> **Current Sprint**: Tape Pricing Validation — can we price loan_tape_2_clean.xlsx and trust the numbers?

---

## Theme 1: Tape Pricing Validation

### Epic 1.1: Effective Life Comparison ✓

Compare the segmentation tree's KM survival curves against APEX2's amort plug to see if they agree on how long these loans live.

- [x] 1.1.1 Extract APEX2 effective life per loan from apex2_comparison.py (NPER + monthly projection methods)
- [x] 1.1.2 Extract KM effective life per loan from segmentation leaf survival curves (month where survival <= 50%)
- [x] 1.1.3 Build side-by-side comparison report: APEX2 vs KM effective life by leaf, by credit band
- [x] 1.1.4 Flag divergences > 2 years — investigate whether APEX2 or KM is more credible for each segment
- [ ] 1.1.5 Document conclusion: which effective life source to use for pricing, or blended approach

> **Status**: Report Section 2 covers 1.1.1–1.1.4 with per-leaf bar charts, divergence badges, and KM survival curve overlay. Remaining: formal recommendation on which life estimate to use.

### Epic 1.2: End-to-End Valuation Dry Run ✓

Run the full valuation pipeline on the tape and sanity-check the numbers.

- [x] 1.2.1 Run valuation on loan_tape_2_clean.xlsx via API (baseline scenario, no MC)
- [x] 1.2.2 Spot-check 5 loans across different leaves — do NPVs, discount margins, and yields pass smell test?
- [x] 1.2.3 Compare portfolio-level WAL (weighted avg life) against APEX2 effective life expectations
- [x] 1.2.4 Run MC valuation (n=100) — check that distribution width is reasonable, not dominated by noise
- [x] 1.2.5 Run all 3 scenarios (baseline/mild/severe) — confirm stress spreads are directionally correct

> **Status**: Complete. Report covers all items: Section 1 (executive summary + ROE), Section 4 (4-model price comparison), Section 5 (directional correctness PASS/FAIL), Section 6 (per-loan detail with implied yields), Section 7 (MC validation with noise diagnostics). CSV export for Excel spot-checking.

### Epic 1.3: Stub Model Impact Assessment ✓

Quantify how much the stub models (DEQ, default, recovery, prepayment) affect the final price vs the real models (survival, segmentation, APEX2).

- [x] 1.3.1 Run valuation with prepayment stub vs with KM survival-derived prepayment — measure NPV delta
- [x] 1.3.2 Sensitivity test: vary DEQ rates +/- 50% — how much does portfolio NPV move?
- [x] 1.3.3 Sensitivity test: vary recovery rates +/- 20% — how much does portfolio NPV move?
- [x] 1.3.4 Rank stub models by pricing impact — which one matters most to replace first?
- [ ] 1.3.5 Write up: "stub risk" summary — which stubs are safe to ship with, which need real data before go-live

> **Status**: Report Section 5 shows model status (real vs stub) and CDR stress sensitivity (0%–2%). Remaining: formal write-up of which stubs are blocking.

### Epic 1.4: Tape-Specific Calibration Check ✓

Verify the tape's loans aren't hitting edge cases or falling outside training data bounds.

- [x] 1.4.1 Check feature distributions: are tape credit/rate/LTV/balance within training data ranges per leaf?
- [x] 1.4.2 Flag any extrapolation risk — loans where features are outside the training convex hull
- [x] 1.4.3 Verify state mapping: do all tape states land in expected state groups?
- [ ] 1.4.4 Check seasoning impact: tape loans are ~55 months old — are KM curves still meaningful at that age?

> **Status**: Report Section 5 has feature distribution vs training range with in-bounds percentages and visual bars. Section 8 has per-leaf training data composition. Remaining: seasoning-specific analysis.

---

## Theme 2: Model Pipeline (Post-Validation)

### Epic 2.1: DVC Setup

Version control for data and model artifacts.

- [ ] 2.1.1 Install DVC, init in project root
- [ ] 2.1.2 Define pipeline stages: training data -> train_segmentation_tree.py -> models/segmentation/
- [ ] 2.1.3 Move models/ to DVC-tracked remote (S3, Azure Blob, or network share)
- [ ] 2.1.4 Document `dvc repro` workflow for Andy

### Epic 2.2: Retraining Automation

- [ ] 2.2.1 Parameterize train_segmentation_tree.py (Freddie sample fraction, max_leaf_nodes, min_samples_leaf)
- [ ] 2.2.2 Add experiment logging — save params + metrics per run to a comparison CSV
- [ ] 2.2.3 Add data validation step — check input files exist and have expected schema before training

### Epic 2.3: Real Model Replacements

Replace stubs with trained models as data becomes available.

- [ ] 2.3.1 Prepayment model — train competing-risk Cox/survival model to replace PSA stub
- [ ] 2.3.2 Delinquency model — train on FNBA servicing data (DPD history)
- [ ] 2.3.3 Default/LGD model — train on FNBA loss data
- [ ] 2.3.4 Recovery model — train on FNBA foreclosure/REO data

---

## Theme 3: Scenario & Reporting (Post-Validation)

### Epic 3.1: Granular Scenario Framework

Replace flat 3-scenario system with per-leaf rate-shift overlays.

- [ ] 3.1.1 Design rate-shift scenarios: parallel shift, twist, inversion
- [ ] 3.1.2 Map rate shifts to prepayment response per segment (in/out of the money)
- [ ] 3.1.3 Add scenario API endpoints with per-leaf stress multipliers
- [ ] 3.1.4 Frontend: scenario comparison view
- [ ] 3.1.5 Correlated MC shocks — add a common economic factor so loans experience systemic stress together, not independently. Current model draws independent lognormal shocks per loan per month (sigma=0.15), which understates portfolio tail risk. Implement a single-factor model: `shock = rho * economy_factor + sqrt(1-rho^2) * idiosyncratic`. Calibrate rho from historical delinquency correlation across segments.
- [ ] 3.1.6 Review scenario severity — current severe (2.5x DEQ, 2x default, 0.65x recovery, 0.4x prepay) is roughly 2008-crisis caliber. May be too harsh for a seasoned 762-FICO / 57%-LTV book. Consider adding a moderate stress tier and benchmarking multipliers against actual FNBA loss history.

### Epic 3.2: Management Reporting

- [x] 3.2.1 Pricing summary report (HTML) — tape-level go/no-go with supporting analysis
- [ ] 3.2.2 Integrate segmentation_report.py output into reporting workflow
- [x] 3.2.3 Export valuation results to Excel for committee review (CSV export in report)

### Epic 3.3: Report Visual Gaps

- [x] 3.3.1 Render KM survival curves in the report — multi-leaf overlay in Section 2 + mini curves per leaf panel in Section 8.
- [ ] 3.3.2 Add engine cashflow curves to the tree leaf panels — restore per-leaf projected cashflow or survival line charts in the leaf detail breakouts.
