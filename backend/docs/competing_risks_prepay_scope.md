# Competing-Risks Prepayment Model — Scope

## Problem Statement

The engine has no standalone prepayment model. Today's options:

| Mode | Default Source | Prepay Source | Problem |
|------|---------------|---------------|---------|
| **stub** | KM all-causes | Stub formula | Double-counts prepay (KM includes it) |
| **km_only** | Flat CDR | KM residual | KM is all-causes, not prepay-specific; collapses to zero for survivor cohorts |
| **APEX2** | Flat CDR | 4-dim lookup | Only calibrated prepay rate we have, but dimensions don't interact (credit×rate) |

The $20M gap between km_only ($60M) and APEX2 ($80M) on the 305-loan tape **is** the value of the prepay model we don't have.

## Why KM Curves Can't Be a Prepay Model

KM survival curves are **all-causes exit curves**. They blend:
- Voluntary payoff (refi, home sale, relocation)
- Default (foreclosure, short sale)
- Curtailment (partial prepay)
- Life events (death, divorce, inheritance)

Decomposing via `prepay = KM_hazard - CDR` doesn't extract a prepay signal — it extracts "everything that isn't default." For seasoned survivors in a rising-rate environment, that's approximately zero, which is the wrong answer. These borrowers will eventually sell homes, divorce, relocate. They just haven't in the last 12 months.

## Why APEX2 Is Incomplete

APEX2 uses 4 independent dimensions averaged:
- **Rate delta**: note rate − 10Y treasury (captures refi incentive) → 1.71 for this tape
- **Credit**: FICO band (captures refi access) → 2.72
- **LTV**: equity band (captures mobility) → 2.24
- **Loan size**: balance band (captures refi savings) → 3.00
- **Average**: 2.37×

The structural flaw: **dimensions don't interact**. High credit (2.72) assumes borrowers CAN and WILL refi. But with rate delta = -1.3% (note rate below market), there's zero refi incentive regardless of credit score. APEX2 can't represent "high credit but no refi motivation" — it averages the two.

For this tape (3.2% coupon, 762 FICO, 57% LTV), APEX2 overstates prepay because it treats credit-driven refi access as always available.

## Target Architecture: Cause-Specific Hazard Model

### Overview

Train separate models for each exit cause:
1. **Voluntary payoff** (refi + home sale): the prepay model
2. **Credit event** (default, short sale, REO): the default model
3. **Censored**: loan still active at observation date

Each model produces a monthly hazard rate h_k(t). The competing-risks framework ensures:
```
S(t) = exp(-∫[h_payoff(s) + h_default(s)] ds)
```
which naturally handles the constraint that a loan can only exit once.

### Data Requirements

**Freddie Mac** (43.8M loans): Raw Freddie Mac loan-level data includes `Zero Balance Code`:
- `01` = Voluntary payoff (prepay)
- `02` = Third-party sale (foreclosure)
- `03` = Short sale
- `06` = REO disposition
- `09` = Deed-in-lieu
- `15` = Note sale (repurchase)

Our current `freddieMacWithCollateralAndState.csv` has only binary `event` (0/1). **Need to re-extract with disposition codes preserved.** Source: Freddie Mac Single-Family Loan-Level Dataset (public, quarterly releases).

**FNBA internal** (42K loans in `fnbaYear.xlsx`): Currently only has `event=1` (all payoffs — no active/censored loans included). Need:
- Full loan history including active loans (event=0)
- Exit reason coding (payoff vs default vs curtailment)
- Servicing system data: payment history, loss mitigation flags

### Model Architecture

```
┌─────────────────────────────────────────────────────┐
│  Input Features (per loan-month)                     │
│  rate_delta, credit, LTV, seasoning, loan_size,     │
│  property_type, state, burnout, seasonality          │
├──────────────┬──────────────────────────────────────┤
│  Payoff Model │  Default Model                       │
│  (XGBoost)    │  (XGBoost)                           │
│  h_payoff(t)  │  h_default(t)                        │
├──────────────┴──────────────────────────────────────┤
│  Competing Risks Integration                         │
│  S(t) = prod[(1 - h_payoff(m))(1 - h_default(m))]  │
│  marginal_prepay(t) = h_payoff(t)                    │
│  marginal_default(t) = h_default(t)                  │
└─────────────────────────────────────────────────────┘
```

**Key features for prepay model:**
- `rate_delta` × `credit` interaction (the missing APEX2 interaction)
- `seasoning` with burnout (prepay rate declines after year 3-5)
- `seasonality` (spring/summer = more home sales)
- `loan_age_bucket` (newly originated vs seasoned)
- `property_type`, `occupancy`, `state` (housing market conditions)

**Key features for default model:**
- `credit`, `LTV`, `dti` (traditional credit risk)
- `modification_flag` (prior distress signal)
- `payment_history` (current/30/60/90 day delinquency)
- `economic_conditions` (unemployment, HPI at origination vs current)

### Phases

| Phase | Deliverable | Effort | Dependency |
|-------|------------|--------|------------|
| **0** | Re-extract Freddie Mac with disposition codes | 1-2 days | Raw quarterly files (~300GB) |
| **1** | Train payoff-specific KM curves per leaf | 2-3 days | Phase 0 |
| **2** | Train XGBoost payoff hazard model | 3-5 days | Phase 0 |
| **3** | Train XGBoost default hazard model | 3-5 days | Phase 0 |
| **4** | Integrate into engine as `prepay_model="competing_risks"` | 2-3 days | Phases 2-3 |
| **5** | Calibrate against APEX2 and FNBA pricing history | 2-3 days | Phase 4 |
| **6** | Retire APEX2 as primary, keep as benchmark | 1 day | Phase 5 |

**Total: ~3-4 weeks of focused work**

### Validation Criteria

1. **Payoff model** should reproduce APEX2 prepay speeds within 20% for rate-incentive-positive loans
2. **Payoff model** should predict materially slower prepay for rate-delta-negative loans (the current gap)
3. **Default model** should produce CDR estimates consistent with 0.1-2.0% annual range for this population
4. **Combined model** portfolio PV should be within 5% of APEX2 for neutral-rate-delta pools
5. **12mo lookback** re-estimation should produce a $3-5M delta (same direction as THR)

### What This Replaces

Once competing risks is live:
- `prepay_model="stub"` → deprecated
- `prepay_model="km_only"` → deprecated (useful as diagnostic only)
- APEX2 multiplier → retained as benchmark/comparison, no longer in pricing path
- KM all-causes curves → replaced by cause-specific KM curves per leaf
- Flat CDR assumption → replaced by default hazard model

### Interim State (Now → Phase 4)

Until competing risks is available, the engine uses APEX2 for prepay with a **rate-environment adjustment** (see `prepay_model="km_rate_adj"`). This:
- Keeps APEX2 as the prepay framework
- Decomposes the multiplier into refi + turnover components
- Zeros out the refi component when rate delta is negative
- Produces a defensible, moderate price delta for 12mo lookback scenarios
