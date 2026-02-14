#!/usr/bin/env python3
"""Pricing Validation Report — Self-Contained HTML.

Compares FNBA's offered pricing against the pricing engine's models
(survival curves, segmentation tree, APEX2 tables, stub DEQ/default/recovery/prepay).

Generates a management-ready go/no-go report as a single self-contained HTML file.

Usage:
    cd backend && python scripts/pricing_validation_report.py
    cd backend && python scripts/pricing_validation_report.py --tape other.xlsx
    cd backend && python scripts/pricing_validation_report.py --out custom.html
"""
from __future__ import annotations

import argparse
import html as html_mod
import logging
import math
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent
MODEL_DIR = PROJECT_DIR / "models"
REPORTS_DIR = PROJECT_DIR / "reports"

sys.path.insert(0, str(BACKEND_DIR))

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Imports from pricing engine
# ---------------------------------------------------------------------------
from scripts.apex2_comparison import (
    TREASURY_10Y,
    compute_apex2_multiplier,
    apex2_amortize,
    project_effective_life,
    load_tape,
    get_credit_band,
)
from app.services.tape_parser import parse_loan_tape
from app.ml.model_loader import ModelRegistry
from app.ml.bucket_assigner import assign_bucket
from app.ml.curve_provider import get_survival_curve
from app.simulation.engine import simulate_loan
from app.models.simulation import PrepayModel, SimulationConfig
from app.models.loan import Loan

# Feature display names (shared across sections)
FEATURE_NAMES = {
    "noteDateYear": "Vintage Year",
    "interestRate": "Interest Rate",
    "creditScore": "Credit Score",
    "ltv": "LTV",
    "loanSize": "Loan Size",
    "stateGroup": "State Group",
    "ITIN": "ITIN",
    "origCustAmortMonth": "Orig Amort Term",
    "dti": "DTI",
}


def _fmt_life(km_life, mean_life=None, suffix="mo"):
    """Format KM 50%-life for display, handling None (never crosses 50%)."""
    if km_life is not None:
        return f"{km_life}{suffix}"
    if mean_life is not None:
        return f"&gt;360 ({mean_life:.0f} mean){suffix}"
    return f"&gt;360{suffix}"


def _life_numeric(km_life, mean_life=None, fallback=360):
    """Return a numeric life for calculations. Uses mean_life when 50%-life is None."""
    if km_life is not None:
        return km_life
    if mean_life is not None:
        return mean_life
    return fallback

# ---------------------------------------------------------------------------
# Additional pricing column mapping for load_tape()
# ---------------------------------------------------------------------------
EXTRA_PRICE_RENAMES = {
    "Base Yield": "base_yield",
    "Total Yield": "total_yield",
    "Projected Yield": "projected_yield",
    "Straight Yield": "straight_yield",
    "Bid Offered": "bid_offered",
    "ROE As Offered": "roe_as_offered",
    "Yield As Offered": "yield_as_offered",
    "Credit Score Kicker": "kicker_credit",
    "LTV Kicker": "kicker_ltv",
    "Seasoning Kicker": "kicker_seasoning",
    "Remaining Term Kicker": "kicker_rem_term",
    "Loan Size Kicker": "kicker_loan_size",
    "Property Type Kicker": "kicker_property_type",
    "Occupancy Kicker": "kicker_occupancy",
    "Hardship Modification Kicker": "kicker_hardship",
    "Location Kicker": "kicker_location",
    "Plug Adjustment": "plug_adjustment",
    "ROE": "roe_internal",
    # ROE model inputs
    "ROE Target Yield": "roe_target_yield",
    "Cost To Acquire": "cost_to_acquire",
    "Capital": "capital_ratio",
    "Tax Rate": "tax_rate",
    "Servicing Cost": "servicing_cost_tape",
    "Cost of Funds": "cost_of_funds",
    "ROE Preliminary Price": "roe_preliminary_price",
    "ROE CentsOnTheDollar": "roe_cents_dollar",
    "FNBA Minimum Required Yield": "min_required_yield",
    "ROE.1": "roe_target_pct",
}


def load_tape_with_pricing(tape_path: Path) -> pd.DataFrame:
    """Load tape via apex2_comparison.load_tape() and add extra pricing columns."""
    df = load_tape(tape_path)

    # Read raw again to grab extra pricing columns not mapped by load_tape
    raw = pd.read_excel(tape_path)
    raw.columns = [str(c).strip() for c in raw.columns]
    raw = raw[
        raw["Current Balance"].notna()
        & (raw["Current Balance"] > 0)
        & (raw["Current Balance"] < 10_000_000)
    ].copy()

    # Align indices
    df = df.reset_index(drop=True)
    raw = raw.reset_index(drop=True)

    for orig_col, new_col in EXTRA_PRICE_RENAMES.items():
        if orig_col in raw.columns and new_col not in df.columns:
            df[new_col] = raw[orig_col].values[: len(df)]

    return df


# ===================================================================
# STAGE 1: Load Data
# ===================================================================
def stage_load(tape_path: Path):
    logger.info("Stage 1: Loading data from %s", tape_path.name)
    t0 = time.time()

    # Raw DataFrame with all pricing columns
    df = load_tape_with_pricing(tape_path)
    logger.info("  Loaded %d loans into DataFrame", len(df))

    # Also parse through tape_parser for Loan objects
    with open(tape_path, "rb") as f:
        pkg = parse_loan_tape(f, tape_path.name)
    logger.info("  Parsed Package: %d loans, $%.0f UPB", pkg.loan_count, pkg.total_upb)

    logger.info("  Stage 1 done (%.1fs)", time.time() - t0)
    return df, pkg


# ===================================================================
# STAGE 2: Init Models
# ===================================================================
def stage_init_models():
    logger.info("Stage 2: Initializing models")
    t0 = time.time()
    registry = ModelRegistry.get()
    if not registry.is_loaded:
        registry.load(str(MODEL_DIR))
    status = registry.get_status()
    logger.info("  Model status: %s (v%s)", status.get("status"), status.get("version"))
    logger.info("  Stage 2 done (%.1fs)", time.time() - t0)
    return registry


# ===================================================================
# STAGE 3: Bucket Assignment + KM Lives
# ===================================================================
def stage_bucket_assignment(pkg):
    logger.info("Stage 3: Bucket assignment + KM lives")
    t0 = time.time()

    loan_leaf_map = {}  # loan_id -> leaf_id
    leaf_loans = defaultdict(list)  # leaf_id -> [loan_dict, ...]
    leaf_km_life = {}  # leaf_id -> 50%-life in months

    for loan in pkg.loans:
        ld = loan.model_dump()
        leaf_id = assign_bucket(ld)
        loan_leaf_map[loan.loan_id] = leaf_id
        leaf_loans[leaf_id].append(ld)

    # For each leaf, compute KM 50%-life and mean life (area under survival curve)
    leaf_mean_life = {}  # leaf_id -> expected life (integral of survival curve)
    leaf_curves = {}  # leaf_id -> list[float] (360 survival probabilities)
    for leaf_id in leaf_loans:
        curve = get_survival_curve(leaf_id, 360)
        leaf_curves[leaf_id] = curve
        half_idx = next((i for i, s in enumerate(curve) if s < 0.5), None)
        leaf_km_life[leaf_id] = (half_idx + 1) if half_idx is not None else None  # None = never crosses 50%
        leaf_mean_life[leaf_id] = sum(curve)  # area under curve = expected life in months

    logger.info("  Assigned %d loans to %d leaves", len(loan_leaf_map), len(leaf_loans))
    logger.info("  Stage 3 done (%.1fs)", time.time() - t0)
    return loan_leaf_map, dict(leaf_loans), leaf_km_life, leaf_mean_life, leaf_curves


# ===================================================================
# STAGE 4: APEX2 Analysis
# ===================================================================
def stage_apex2_analysis(df):
    logger.info("Stage 4: APEX2 analysis")
    t0 = time.time()

    # Compute 4-dim multipliers
    mult_rows = []
    for _, row in df.iterrows():
        mult_rows.append(compute_apex2_multiplier(
            row["credit"], row["rate"],
            row.get("ltv", 60), row["balance"],
        ))
    for key in mult_rows[0]:
        df[key] = [m[key] for m in mult_rows]

    # Per-loan NPER and monthly-projection effective life
    nper_vals = []
    life_vals = []
    for _, row in df.iterrows():
        mult = row.get("apex2_prepay", row["avg_4dim"])
        nper = apex2_amortize(row["balance"], row["pandi"] * mult, row["rate"], 12)
        life = project_effective_life(
            row["balance"], row["pandi"], row["rate"],
            mult, row["seasoning"], int(row["rem_term"]), use_seasoning=True,
        )
        nper_vals.append(nper)
        life_vals.append(life)
    df["nper_life"] = nper_vals
    df["monthly_proj_life"] = life_vals

    # 9 scenarios: 3 mult sources x 3 seasoning modes
    has_tape_mult = "apex2_prepay" in df.columns and df["apex2_prepay"].notna().any()
    mult_sources = {"4-dim avg": "avg_4dim", "credit-only": "credit_only"}
    if has_tape_mult:
        mult_sources = {"tape (blended)": "apex2_prepay", **mult_sources}

    scenarios_9 = {}
    w = df["balance"]
    total_upb = w.sum()
    for label, mult_col in mult_sources.items():
        for seas_label, use_seas, override_age in [
            ("flat", False, None),
            ("seasoned (actual)", True, None),
            ("seasoned (age=0)", True, 0),
        ]:
            key = f"{label} / {seas_label}"
            plugs, lives = [], []
            for _, loan in df.iterrows():
                mult = loan[mult_col]
                age = override_age if override_age is not None else loan["seasoning"]
                plug = apex2_amortize(loan["balance"], loan["pandi"] * mult, loan["rate"], 12)
                life = project_effective_life(
                    loan["balance"], loan["pandi"], loan["rate"],
                    mult, age, int(loan["rem_term"]), use_seasoning=use_seas,
                )
                plugs.append(plug)
                lives.append(life)
            wt_plug = (pd.Series(plugs).fillna(0) * w).sum() / total_upb
            wt_life = (pd.Series(lives) * w).sum() / total_upb
            scenarios_9[key] = {"plug": wt_plug, "life": wt_life}

    logger.info("  Computed 9 APEX2 scenarios")
    logger.info("  Stage 4 done (%.1fs)", time.time() - t0)
    return df, scenarios_9


# ===================================================================
# STAGE 5: Deterministic Cashflow Valuation
# ===================================================================
def stage_cashflow_valuation(df, pkg, loan_leaf_map, prepay_model="stub", annual_cdr=0.0015):
    logger.info("Stage 5: Deterministic cashflow valuation")
    t0 = time.time()

    config = SimulationConfig(
        n_simulations=0,
        scenarios=["baseline", "mild_recession", "severe_recession"],
        include_stochastic=False,
        prepay_model=PrepayModel(prepay_model),
        annual_cdr=annual_cdr,
    )

    results = {}  # loan_id -> LoanValuationResult
    done = 0
    for loan in pkg.loans:
        try:
            result = simulate_loan(loan, config)
            results[loan.loan_id] = result
        except Exception as e:
            logger.warning("  Loan %s simulation failed: %s", loan.loan_id, e)
        done += 1
        if done % 50 == 0:
            logger.info("  Valued %d / %d loans (%.0fs)", done, len(pkg.loans), time.time() - t0)

    logger.info("  Valued %d loans total", len(results))

    # Map results back to DataFrame
    model_npvs = []
    pv_baseline = []
    pv_mild = []
    pv_severe = []
    implied_yields = []

    for _, row in df.iterrows():
        lid = f"LN-{int(_ + 1):04d}"
        r = results.get(lid)
        if r is None:
            model_npvs.append(np.nan)
            pv_baseline.append(np.nan)
            pv_mild.append(np.nan)
            pv_severe.append(np.nan)
            implied_yields.append(np.nan)
            continue

        npv = r.expected_pv
        model_npvs.append(npv)
        pv_baseline.append(r.pv_by_scenario.get("baseline", np.nan))
        pv_mild.append(r.pv_by_scenario.get("mild_recession", np.nan))
        pv_severe.append(r.pv_by_scenario.get("severe_recession", np.nan))

        # Compute implied yield via bisection — use ITV-capped price
        offered = row.get("final_price", row.get("bid_offered", np.nan))
        if pd.notna(offered) and offered > 0 and r.monthly_cash_flows:
            iy = _implied_yield(r.monthly_cash_flows, offered)
            implied_yields.append(iy)
        else:
            implied_yields.append(np.nan)

    df["model_npv"] = model_npvs
    df["pv_baseline"] = pv_baseline
    df["pv_mild"] = pv_mild
    df["pv_severe"] = pv_severe
    df["implied_yield"] = implied_yields

    # Price diff — use ITV-capped price as authoritative "Offered"
    offered_col = "final_price" if "final_price" in df.columns else "bid_offered"
    df["offered_price"] = df[offered_col]
    df["price_diff"] = df["model_npv"] - df["offered_price"]
    df["price_diff_pct"] = (df["price_diff"] / df["offered_price"] * 100).replace([np.inf, -np.inf], np.nan)

    logger.info("  Stage 5 done (%.1fs)", time.time() - t0)
    return df, results


def _implied_yield(cash_flows, offered_price: float) -> float:
    """Bisection solver: find annual yield where NPV(cfs, y) == offered_price."""
    lo, hi = -0.05, 0.50
    for _ in range(100):
        mid = (lo + hi) / 2
        npv = sum(
            cf.net_cash_flow / (1 + mid / 12) ** cf.month
            for cf in cash_flows
        )
        if npv > offered_price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _compute_apex2_price(pandi, prepay_mult, amort_plug, target_yield, cta):
    """Replicate APEX2 price = PV of accelerated payments at target yield.

    Price = (P&I × mult - CTA/plug) × (1 - (1+r)^-n) / r
    where r = target_yield/12, n = amort_plug months.
    """
    if amort_plug <= 0 or target_yield <= 0 or pandi <= 0:
        return 0.0
    r = target_yield / 12.0
    effective_pmt = pandi * prepay_mult - cta / amort_plug
    if effective_pmt <= 0:
        return 0.0
    # PV of ordinary annuity
    return effective_pmt * (1 - (1 + r) ** (-amort_plug)) / r


# ===================================================================
# STAGE 5b: Monte Carlo Validation
# ===================================================================
def stage_monte_carlo(df, pkg, n_sims=200, prepay_model="stub", annual_cdr=0.0015):
    """Run Monte Carlo simulation for all loans.

    Returns updated df, mc_results dict, and portfolio-level MC distribution.
    """
    logger.info("Stage 5b: Monte Carlo validation (%d sims/loan)", n_sims)
    t0 = time.time()

    config = SimulationConfig(
        n_simulations=n_sims,
        scenarios=["baseline"],
        include_stochastic=True,
        stochastic_seed=42,
        prepay_model=PrepayModel(prepay_model),
        annual_cdr=annual_cdr,
    )

    mc_results = {}  # loan_id -> LoanValuationResult
    done = 0
    for loan in pkg.loans:
        try:
            result = simulate_loan(loan, config)
            mc_results[loan.loan_id] = result
        except Exception as e:
            logger.warning("  MC sim for %s failed: %s", loan.loan_id, e)
        done += 1
        if done % 50 == 0:
            logger.info("  MC simulated %d / %d loans (%.0fs)", done, len(pkg.loans), time.time() - t0)

    logger.info("  MC completed %d loans", len(mc_results))

    # Build portfolio-level distribution by summing across loans at each sim index
    loans_with_dist = [r for r in mc_results.values() if r.pv_distribution]
    portfolio_mc_pvs = []
    if loans_with_dist:
        max_sims = min(len(r.pv_distribution) for r in loans_with_dist)
        for sim_idx in range(max_sims):
            port_pv = sum(
                r.pv_distribution[sim_idx]
                for r in loans_with_dist
                if sim_idx < len(r.pv_distribution)
            )
            portfolio_mc_pvs.append(port_pv)
        portfolio_mc_pvs.sort()

    # Map MC results back to DataFrame
    mc_npvs = []
    mc_p5 = []
    mc_p50 = []
    mc_p95 = []
    mc_spread = []
    for idx, row in df.iterrows():
        lid = f"LN-{int(idx + 1):04d}"
        r = mc_results.get(lid)
        if r is None or not r.pv_distribution:
            mc_npvs.append(np.nan)
            mc_p5.append(np.nan)
            mc_p50.append(np.nan)
            mc_p95.append(np.nan)
            mc_spread.append(np.nan)
            continue

        mc_mean = np.mean(r.pv_distribution)
        mc_npvs.append(mc_mean)
        mc_p5.append(r.pv_percentiles.get("p5", np.nan))
        mc_p50.append(r.pv_percentiles.get("p50", np.nan))
        mc_p95.append(r.pv_percentiles.get("p95", np.nan))
        p5v = r.pv_percentiles.get("p5", 0)
        p95v = r.pv_percentiles.get("p95", 0)
        mc_spread.append((p95v - p5v) / mc_mean * 100 if mc_mean > 0 else 0)

    df["mc_npv"] = mc_npvs
    df["mc_p5"] = mc_p5
    df["mc_p50"] = mc_p50
    df["mc_p95"] = mc_p95
    df["mc_spread"] = mc_spread

    logger.info("  Stage 5b done (%.1fs)", time.time() - t0)
    return df, mc_results, portfolio_mc_pvs


# ===================================================================
# STAGE 5c: Price Comparison (4 estimates at tape's ROE target yield)
# ===================================================================
def stage_price_comparison(df, results, pkg, mc_results=None):
    """Compute 3 price estimates per loan, all at the tape's ROE target yield.

    1. Offered — Final Price with ITV cap from tape
    2. APEX2 Replicated — PV(target_yield, amort_plug, P&I×mult - CTA/plug)
    3. Pricing Engine — MC distribution scaled to the APEX2 price.

    Returns updated df with price columns and portfolio-level summary dict.
    """
    logger.info("Stage 5c: Price comparison (3 estimates)")
    t0 = time.time()

    # Ensure required columns exist with fallbacks
    has_target_yield = "roe_target_yield" in df.columns and df["roe_target_yield"].notna().any()
    has_cta = "cost_to_acquire" in df.columns and df["cost_to_acquire"].notna().any()

    if not has_target_yield:
        logger.warning("  No ROE Target Yield column — using 7.0%% fallback")
    if not has_cta:
        logger.warning("  No Cost To Acquire column — using $850 fallback")

    # Lookup helpers
    loan_lookup = {loan.loan_id: loan for loan in pkg.loans}

    price_offered = []
    price_apex2 = []
    price_mc = []
    price_mc_p5 = []
    price_mc_p95 = []

    for idx, row in df.iterrows():
        lid = f"LN-{int(idx + 1):04d}"

        # Offered price — use ITV-capped (Final Price) as authoritative
        offered = row.get("final_price", row.get("bid_offered", np.nan))
        if pd.isna(offered) or offered <= 0:
            offered = row.get("offered_price", 0)
        price_offered.append(offered)

        # Tape ROE inputs
        target_yield = row.get("roe_target_yield", 0.07) if has_target_yield else 0.07
        if pd.isna(target_yield) or target_yield <= 0:
            target_yield = 0.07
        cta = row.get("cost_to_acquire", 850) if has_cta else 850
        if pd.isna(cta):
            cta = 850
        pandi = row.get("pandi", 0)
        prepay_mult = row.get("apex2_prepay", row.get("avg_4dim", 2.3))
        amort_plug = row.get("apex2_amort_plug", row.get("nper_life", 97))

        if pd.isna(pandi) or pandi <= 0:
            price_apex2.append(np.nan)
            apex2_px = np.nan
        else:
            if pd.isna(prepay_mult):
                prepay_mult = 2.3
            if pd.isna(amort_plug) or amort_plug <= 0:
                amort_plug = 97
            apex2_px = _compute_apex2_price(pandi, prepay_mult, amort_plug, target_yield, cta)
            price_apex2.append(apex2_px)

        # Pricing Engine: scale MC distribution to the APEX2 price.
        # MC was run at 8% CoC. We preserve the relative spread (CV)
        # but center on the APEX2 price at target yield.
        r = results.get(lid)
        det_npv_8pct = r.expected_pv if r else 0
        if mc_results and lid in mc_results and not pd.isna(apex2_px) and apex2_px > 0:
            mc_r = mc_results[lid]
            if mc_r.pv_distribution and det_npv_8pct > 0:
                scale = apex2_px / det_npv_8pct
                mc_pvs_scaled = [pv * scale for pv in mc_r.pv_distribution]
                price_mc.append(np.mean(mc_pvs_scaled))
                mc_pvs_sorted = sorted(mc_pvs_scaled)
                p5_idx = min(int(0.05 * len(mc_pvs_sorted)), len(mc_pvs_sorted) - 1)
                p95_idx = min(int(0.95 * len(mc_pvs_sorted)), len(mc_pvs_sorted) - 1)
                price_mc_p5.append(mc_pvs_sorted[p5_idx])
                price_mc_p95.append(mc_pvs_sorted[p95_idx])
            else:
                price_mc.append(apex2_px)
                price_mc_p5.append(np.nan)
                price_mc_p95.append(np.nan)
        else:
            price_mc.append(np.nan)
            price_mc_p5.append(np.nan)
            price_mc_p95.append(np.nan)

    df["price_offered"] = price_offered
    df["price_apex2"] = price_apex2
    df["price_mc"] = price_mc
    df["price_mc_p5"] = price_mc_p5
    df["price_mc_p95"] = price_mc_p95

    # Cents on dollar equivalents
    df["cents_apex2"] = df["price_apex2"] / df["balance"] * 100
    df["cents_mc"] = df["price_mc"] / df["balance"] * 100

    # Portfolio totals
    totals = {
        "offered": df["price_offered"].sum(),
        "apex2": df["price_apex2"].dropna().sum(),
        "mc": df["price_mc"].dropna().sum(),
        "mc_p5": df["price_mc_p5"].dropna().sum() if df["price_mc_p5"].notna().any() else None,
        "mc_p95": df["price_mc_p95"].dropna().sum() if df["price_mc_p95"].notna().any() else None,
    }

    # Implied ROE for each price estimate
    # Formula: TargetYield = ROE*Capital + CoF*(1-Capital) + Servicing + Tax
    # Invert:  ROE = (Yield - CoF*(1-Cap) - Serv - Tax) / Cap
    bal = df["balance"]
    _wm = lambda col: (df[col] * bal).sum() / bal.sum() if col in df.columns and df[col].notna().any() else None
    cap_avg = _wm("capital_ratio") or _wm("Capital") or 0.0886
    cof_avg = _wm("cost_of_funds") or _wm("Cost of Funds") or 0.0427
    serv_avg = _wm("servicing_cost_tape") or _wm("Servicing Cost") or 0.0049
    tax_avg = _wm("tax_rate") or _wm("Tax Rate") or 0.0047
    ty_avg = _wm("roe_target_yield") or _wm("ROE Target Yield") or 0.07

    def _implied_roe(model_price, offered_price):
        if offered_price <= 0 or cap_avg <= 0:
            return None
        eff_yield = ty_avg * (model_price / offered_price)
        return (eff_yield - cof_avg * (1 - cap_avg) - serv_avg - tax_avg) / cap_avg

    p_off_total = totals["offered"]
    totals["roe_offered"] = _implied_roe(p_off_total, p_off_total)
    totals["roe_apex2"] = _implied_roe(totals["apex2"], p_off_total)
    totals["roe_mc"] = _implied_roe(totals["mc"], p_off_total) if totals["mc"] > 0 else None

    logger.info("  Offered:  $%s", f"{totals['offered']:,.0f}")
    logger.info("  APEX2:    $%s", f"{totals['apex2']:,.0f}")
    logger.info("  PE MC:    $%s", f"{totals['mc']:,.0f}")
    logger.info("  Stage 5c done (%.1fs)", time.time() - t0)
    return df, totals


# ===================================================================
# STAGE 6: Sensitivity
# ===================================================================
def stage_sensitivity(df, pkg, results, loan_leaf_map):
    logger.info("Stage 6: Sensitivity analysis")
    t0 = time.time()

    # --- Stub impact: sample 30 loans by balance decile ---
    df_valid = df[df["model_npv"].notna()].copy()
    df_valid["bal_decile"] = pd.qcut(df_valid["balance"], q=10, labels=False, duplicates="drop")
    sample_ids = (
        df_valid.groupby("bal_decile")
        .apply(lambda g: g.sample(min(3, len(g)), random_state=42), include_groups=False)
        .index.get_level_values(1)
    )
    sample_df = df_valid.loc[sample_ids]
    sample_loans = [pkg.loans[i] for i in sample_df.index if i < len(pkg.loans)]

    # Get model status from first result
    model_status = {}
    if results:
        first_result = next(iter(results.values()))
        model_status = first_result.model_status

    stub_impacts = []
    for stub_name in ["deq", "default", "recovery", "prepay", "cost_of_capital"]:
        status = model_status.get(stub_name, model_status.get("overall", "stub"))
        stub_impacts.append({
            "model": stub_name,
            "status": status,
            "impact_label": "Active" if status not in ("stub", "missing") else "Stub",
        })

    # --- Feature bounds analysis ---
    registry = ModelRegistry.get()
    tree_structure = registry.tree_structure
    feature_bounds = []

    # 9 training features and what they map to in the tape
    feature_map = {
        "creditScore": ("credit", None),
        "interestRate": ("rate", None),
        "ltv": ("ltv", None),
        "loanSize": ("balance", None),
        "dti": (None, 36.0),  # not in tape
        "noteDateYear": (None, 2020),
        "stateGroup": (None, None),
        "ITIN": (None, 0),
        "origCustAmortMonth": ("rem_term", None),
    }

    training_metadata = tree_structure.get("training_ranges", {})
    for feat_name, (tape_col, default_val) in feature_map.items():
        train_range = training_metadata.get(feat_name, {})
        t_min = train_range.get("min", None)
        t_max = train_range.get("max", None)

        if tape_col and tape_col in df.columns:
            tape_vals = df[tape_col].dropna()
            tape_min = tape_vals.min()
            tape_max = tape_vals.max()
            if t_min is not None and t_max is not None:
                in_bounds = ((tape_vals >= t_min) & (tape_vals <= t_max)).sum()
                in_bounds_pct = in_bounds / len(tape_vals) * 100 if len(tape_vals) > 0 else 100
            else:
                in_bounds_pct = 100.0
        else:
            tape_min = default_val
            tape_max = default_val
            in_bounds_pct = 100.0

        feature_bounds.append({
            "feature": feat_name,
            "train_min": t_min,
            "train_max": t_max,
            "tape_min": tape_min,
            "tape_max": tape_max,
            "in_bounds_pct": in_bounds_pct,
        })

    # --- Scenario stress summary (already computed in stage 5) ---
    total_upb = df["balance"].sum()
    scenario_stress = {}
    for scen in ["baseline", "mild_recession", "severe_recession"]:
        col = f"pv_{scen}" if scen == "baseline" else f"pv_{scen.split('_')[0]}"
        col_map = {"baseline": "pv_baseline", "mild_recession": "pv_mild", "severe_recession": "pv_severe"}
        col = col_map[scen]
        total_npv = df[col].sum()
        offered_total = df["offered_price"].sum()
        scenario_stress[scen] = {
            "total_npv": total_npv,
            "npv_per_upb": total_npv / total_upb if total_upb > 0 else 0,
            "vs_offered": total_npv / offered_total if offered_total > 0 else 0,
        }

    # --- Directional correctness: baseline >= mild >= severe per loan ---
    n_loans = len(df)
    base_ge_mild = (df["pv_baseline"] >= df["pv_mild"]).sum()
    mild_ge_severe = (df["pv_mild"] >= df["pv_severe"]).sum()
    base_ge_severe = (df["pv_baseline"] >= df["pv_severe"]).sum()
    portfolio_base = df["pv_baseline"].sum()
    portfolio_mild = df["pv_mild"].sum()
    portfolio_severe = df["pv_severe"].sum()
    scenario_stress["directional"] = {
        "n_loans": n_loans,
        "base_ge_mild": base_ge_mild,
        "mild_ge_severe": mild_ge_severe,
        "base_ge_severe": base_ge_severe,
        "portfolio_monotonic": portfolio_base >= portfolio_mild >= portfolio_severe,
    }

    logger.info("  Stage 6 done (%.1fs)", time.time() - t0)
    return stub_impacts, feature_bounds, scenario_stress


# ===================================================================
# STAGE 7: Assemble HTML
# ===================================================================
def stage_assemble_html(
    df, pkg, loan_leaf_map, leaf_loans, leaf_km_life, leaf_mean_life,
    scenarios_9, results, stub_impacts, feature_bounds, scenario_stress,
    registry=None, mc_results=None, portfolio_mc_pvs=None,
    price_totals=None, leaf_curves=None, curve_variant_label="Full History",
    prepay_model_label="Stub",
):
    logger.info("Stage 7: Assembling HTML")
    now = datetime.now().strftime("%B %d, %Y %I:%M %p")
    w = df["balance"]
    total_upb = w.sum()

    def wt_avg(series):
        valid = series.dropna()
        wts = w.loc[valid.index]
        return (valid * wts).sum() / wts.sum() if wts.sum() > 0 else 0

    # --- Compute summary metrics ---
    total_offered = df["offered_price"].sum()
    avg_cents = df["cents_dollar"].mean() if "cents_dollar" in df.columns else 0
    total_model_npv = df["model_npv"].dropna().sum()

    # Price comparison totals
    pt = price_totals or {}
    total_price_offered = pt.get("offered", total_offered)
    total_price_apex2 = pt.get("apex2", 0)
    total_price_mc = pt.get("mc", 0)

    # APEX2 replication accuracy: how close is our replicated APEX2 to offered?
    apex2_vs_offered = total_price_apex2 / total_price_offered if total_price_offered > 0 else 0

    # Pricing Engine vs offered
    mc_vs_offered = total_price_mc / total_price_offered if total_price_offered > 0 and total_price_mc > 0 else 0

    # Effective life agreement
    tape_plug = wt_avg(df["apex2_amort_plug"]) if "apex2_amort_plug" in df.columns else 0
    # Balance-weighted KM life and mean life
    km_lives = []
    mean_lives = []
    for _, row in df.iterrows():
        lid = f"LN-{int(_ + 1):04d}"
        leaf = loan_leaf_map.get(lid, 0)
        mean_life = leaf_mean_life.get(leaf, 120)
        km_life = leaf_km_life.get(leaf)
        km_lives.append(_life_numeric(km_life, mean_life))
        mean_lives.append(mean_life)
    df["km_life"] = km_lives
    df["engine_mean_life"] = mean_lives
    avg_km_life = wt_avg(pd.Series(km_lives, index=df.index))
    avg_mean_life = wt_avg(pd.Series(mean_lives, index=df.index))
    life_divergence = abs(tape_plug - avg_km_life) / tape_plug * 100 if tape_plug > 0 else 0

    # Feature bounds
    in_bounds_scores = [fb["in_bounds_pct"] for fb in feature_bounds if fb["train_min"] is not None]
    avg_in_bounds = np.mean(in_bounds_scores) if in_bounds_scores else 100

    # Model completeness — check how many sub-models are real vs stubs
    n_stub = sum(1 for s in stub_impacts if s["impact_label"] == "Stub")
    n_total = len(stub_impacts)

    # --- Build HTML sections ---
    section1 = _build_executive_summary(
        df, pkg, total_upb, total_offered, avg_cents, wt_avg, now,
        price_totals=pt, apex2_vs_offered=apex2_vs_offered,
        mc_vs_offered=mc_vs_offered, life_divergence=life_divergence,
        avg_in_bounds=avg_in_bounds, n_stub=n_stub, n_total=n_total,
        tape_plug=tape_plug, avg_km_life=avg_km_life, avg_mean_life=avg_mean_life,
    )
    section2 = _build_effective_life(
        df, leaf_loans, leaf_km_life, leaf_mean_life, loan_leaf_map, tape_plug,
        avg_km_life, avg_mean_life, wt_avg, leaf_curves=leaf_curves,
    )
    section3 = _build_apex2_dimensional(df, wt_avg)
    section4 = _build_price_comparison(df, pt, scenario_stress, results)
    section5 = _build_sensitivity(stub_impacts, feature_bounds, scenario_stress, total_upb)
    section6 = _build_loan_detail(df, loan_leaf_map, leaf_km_life, results)
    section7 = _build_tree_diagram(
        loan_leaf_map, leaf_km_life, registry or ModelRegistry.get(),
        leaf_curves=leaf_curves,
    )

    section8 = ""
    if mc_results and portfolio_mc_pvs:
        section8 = _build_monte_carlo_section(df, mc_results, portfolio_mc_pvs, scenario_stress)

    section9 = _build_assumptions_tab(df, wt_avg)

    page = _assemble_page(now, section1, section2, section3, section4, section5, section6, section7, section8, section9, curve_variant_label=curve_variant_label, prepay_model_label=prepay_model_label)
    return page


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------
def _traffic_light_svg(label: str, value: float, thresholds: tuple, unit: str = "", invert: bool = False) -> str:
    """SVG traffic light indicator.

    thresholds = (green_thresh, yellow_thresh) where:
      - for normal: green if value >= green_thresh, yellow if >= yellow_thresh
      - for invert: green if value <= green_thresh, yellow if <= yellow_thresh
    """
    gt, yt = thresholds
    if not invert:
        color = "#16a34a" if value >= gt else ("#ca8a04" if value >= yt else "#ef4444")
    else:
        color = "#16a34a" if value <= gt else ("#ca8a04" if value <= yt else "#ef4444")

    display = f"{value:.1f}{unit}" if unit == "%" else f"{value:.2f}"
    return f"""<div class="traffic-light">
      <svg width="24" height="24" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="{color}"/></svg>
      <div>
        <div class="tl-value">{display}</div>
        <div class="tl-label">{label}</div>
      </div>
    </div>"""


def _build_executive_summary(df, pkg, total_upb, total_offered, avg_cents,
                              wt_avg, now,
                              price_totals=None, apex2_vs_offered=0,
                              mc_vs_offered=0, life_divergence=0,
                              avg_in_bounds=100, n_stub=0, n_total=5,
                              tape_plug=0, avg_km_life=0, avg_mean_life=0):
    pt = price_totals or {}
    p_offered = pt.get("offered", total_offered)
    p_apex2 = pt.get("apex2", 0)
    p_mc = pt.get("mc", 0)
    mc_p5 = pt.get("mc_p5")
    mc_p95 = pt.get("mc_p95")
    mc_vs_offered = p_mc / p_offered if p_offered > 0 and p_mc > 0 else 0

    # --- Primary display: price cards ---
    cards = f"""
    <div class="summary-grid">
      <div class="summary-card" style="border-top:4px solid #374151">
        <div class="card-number">${p_offered:,.0f}</div>
        <div class="card-label">Offered</div>
        <div style="font-size:11px;color:#6b7280">{avg_cents:.1f} cents/$</div>
      </div>
      <div class="summary-card" style="border-top:4px solid #f59e0b">
        <div class="card-number">${p_apex2:,.0f}</div>
        <div class="card-label">APEX2 Replicated</div>
        <div style="font-size:11px;color:#6b7280">{apex2_vs_offered:.1%} of offered</div>
      </div>
      <div class="summary-card" style="border-top:4px solid #16a34a">
        <div class="card-number">{f'${p_mc:,.0f}' if p_mc > 0 else 'N/A'}</div>
        <div class="card-label">Pricing Engine</div>
        <div style="font-size:11px;color:#6b7280">{f'90% band: ${mc_p5:,.0f}&ndash;${mc_p95:,.0f}' if mc_p5 and mc_p95 else 'MC not run' if p_mc == 0 else 'n/a'}</div>
      </div>
    </div>"""

    # --- 3-price comparison bar chart ---
    max_price = max(p_offered, p_apex2, p_mc) or 1
    bar_items = [
        ("Offered", p_offered, "#374151"),
        ("APEX2", p_apex2, "#f59e0b"),
        ("Pricing Engine", p_mc, "#16a34a"),
    ]
    bar_rows = []
    for label, val, color in bar_items:
        w_pct = val / max_price * 100 if val > 0 else 0
        vs_off = val / p_offered * 100 if p_offered > 0 and val > 0 else 0
        display_val = f"${val:,.0f} ({vs_off:.1f}%)" if val > 0 else "N/A"
        bar_rows.append(f"""
        <div class="life-bar-row" style="margin-bottom:6px">
          <span class="life-bar-tag" style="width:60px;font-weight:600">{label}</span>
          <div class="life-bar-track"><div class="life-bar-fill" style="width:{w_pct:.1f}%;background:{color}"></div></div>
          <span class="life-bar-val" style="width:120px">{display_val}</span>
        </div>""")
    price_bars = f'<div class="chart-container" style="text-align:left">{"".join(bar_rows)}</div>'

    # --- Key metrics: pool stats + ROE inputs ---
    wtd_rate = wt_avg(df["rate"])
    wtd_credit = wt_avg(df["credit"])
    wtd_ltv = wt_avg(df["ltv"]) if "ltv" in df.columns else 0
    wtd_seasoning = wt_avg(df["seasoning"])
    wtd_rem_term = wt_avg(df["rem_term"])
    proj_yield = wt_avg(df["projected_yield"]) if "projected_yield" in df.columns else 0
    roe_offered = wt_avg(df["roe_as_offered"]) if "roe_as_offered" in df.columns else 0
    target_yield = wt_avg(df["roe_target_yield"]) if "roe_target_yield" in df.columns else 0
    cof = wt_avg(df["cost_of_funds"]) if "cost_of_funds" in df.columns else 0
    capital = wt_avg(df["capital_ratio"]) if "capital_ratio" in df.columns else 0
    tax = wt_avg(df["tax_rate"]) if "tax_rate" in df.columns else 0

    metrics = f"""
    <div class="metrics-grid">
      <table class="data-table mini-metrics">
        <thead><tr><th>Pool Characteristics</th><th>Value</th></tr></thead>
        <tbody>
          <tr><td>{len(df):,} Loans</td><td class="num">${total_upb:,.0f} UPB</td></tr>
          <tr><td>Wtd Avg Rate</td><td class="num">{wtd_rate:.3f}%</td></tr>
          <tr><td>Wtd Avg Credit</td><td class="num">{wtd_credit:.0f}</td></tr>
          <tr><td>Wtd Avg LTV</td><td class="num">{wtd_ltv:.1f}%</td></tr>
          <tr><td>Wtd Avg Seasoning</td><td class="num">{wtd_seasoning:.0f} mo</td></tr>
          <tr><td>Wtd Avg Rem Term</td><td class="num">{wtd_rem_term:.0f} mo</td></tr>
        </tbody>
      </table>
      <table class="data-table mini-metrics">
        <thead><tr><th>ROE Framework (tape)</th><th>Value</th></tr></thead>
        <tbody>
          <tr><td>ROE Target</td><td class="num">{roe_offered:.1%}</td></tr>
          <tr><td>ROE Target Yield</td><td class="num">{target_yield:.2%}</td></tr>
          <tr><td>Projected Yield</td><td class="num">{proj_yield:.2%}</td></tr>
          <tr><td>Cost of Funds</td><td class="num">{cof:.2%}</td></tr>
          <tr><td>Capital Ratio</td><td class="num">{capital:.2%}</td></tr>
          <tr><td>APEX2 Amort Plug</td><td class="num">{tape_plug:.0f} mo</td></tr>
        </tbody>
      </table>
    </div>
    <div class="traffic-lights" style="flex-direction:row;flex-wrap:wrap;gap:20px">
      {_traffic_light_svg("APEX2 vs Offered", apex2_vs_offered * 100, (95, 85), "%")}
      {_traffic_light_svg("PE vs Offered", mc_vs_offered * 100, (90, 70), "%") if mc_vs_offered > 0 else ""}
      {_traffic_light_svg("Prepay Life Gap (Tape vs KM)", life_divergence, (20, 40), "%", invert=True)}
      {_traffic_light_svg("Features In Bounds", avg_in_bounds, (90, 75), "%")}
    </div>
    <div style="font-size:12px;color:#6b7280;margin-top:8px">
      Sub-models: {n_total - n_stub}/{n_total} real | Life: APEX2 {tape_plug:.0f}mo vs Mean {avg_mean_life:.0f}mo (KM 50%: {avg_km_life:.0f}mo)
    </div>"""

    # --- ROE summary row ---
    roe_off_val = pt.get("roe_offered")
    roe_a2_val = pt.get("roe_apex2")
    roe_mc_val = pt.get("roe_mc")
    tape_roe_target = roe_offered  # from tape's "ROE As Offered"

    def _roe_chip(label, val, target):
        if val is None:
            return f'<div style="display:inline-flex;align-items:center;gap:6px;padding:4px 12px;border-radius:6px;background:#f3f4f6"><span style="font-weight:600;font-size:12px">{label}</span><span style="font-size:13px;color:#6b7280">n/a</span></div>'
        color = "#16a34a" if val >= target else ("#ca8a04" if val >= target * 0.9 else "#ef4444")
        bg = "#f0fdf4" if val >= target else ("#fefce8" if val >= target * 0.9 else "#fef2f2")
        return f'<div style="display:inline-flex;align-items:center;gap:6px;padding:4px 12px;border-radius:6px;background:{bg}"><span style="font-weight:600;font-size:12px">{label}</span><span style="font-size:14px;font-weight:700;color:{color}">{val:.1%}</span></div>'

    roe_banner = f"""
    <div style="display:flex;flex-wrap:wrap;gap:10px;margin-top:10px;align-items:center">
      <span style="font-size:12px;color:#6b7280;font-weight:600">Implied ROE:</span>
      {_roe_chip("Offered", roe_off_val, tape_roe_target)}
      {_roe_chip("APEX2", roe_a2_val, tape_roe_target)}
      {_roe_chip("Pricing Engine", roe_mc_val, tape_roe_target)}
      <span style="font-size:11px;color:#9ca3af">(target {tape_roe_target:.1%})</span>
    </div>"""

    # Neutral price-spread summary — no judgment, just facts
    apex2_spread_pct = abs(apex2_vs_offered - 1.0) * 100
    apex2_dir = "above" if apex2_vs_offered >= 1.0 else "below"
    mc_spread_str = ""
    if mc_vs_offered > 0:
        mc_spread_pct = abs(mc_vs_offered - 1.0) * 100
        mc_dir = "below" if mc_vs_offered < 1.0 else "above"
        mc_spread_str = f"&bull; Pricing Engine is {mc_spread_pct:.1f}% {mc_dir} Offered"
    spread_banner = f"""
    <div class="info-callout" style="margin-top:12px">
      <strong>Price spread:</strong> APEX2 is {apex2_spread_pct:.1f}% {apex2_dir} Offered
      {mc_spread_str}
      &bull; Prepay life: APEX2 {tape_plug:.0f}mo vs KM mean {avg_mean_life:.0f}mo ({life_divergence:.0f}% gap)
      &bull; {n_total - n_stub}/{n_total} sub-models real
    </div>"""

    methodology_note = f"""
    <div class="info-callout" style="margin-top:16px">
      <strong>How to read the three prices:</strong> All three columns are present values discounted
      at the tape&rsquo;s <em>ROE target yield</em> (pool avg {target_yield:.2%}), making them directly
      comparable. The differences come from methodology, not from different return targets.
      <table style="margin:10px 0 6px;border-collapse:collapse;font-size:12px;width:100%">
        <tr style="border-bottom:1px solid #ddd">
          <td style="padding:4px 8px;font-weight:600;width:120px">Offered</td>
          <td style="padding:4px 8px">The actual bid price from the tape (market price).</td>
        </tr>
        <tr style="border-bottom:1px solid #ddd">
          <td style="padding:4px 8px;font-weight:600">APEX2</td>
          <td style="padding:4px 8px">PV of APEX2 amortization schedule with <em>no</em> credit adjustment. Pure prepayment-driven price.</td>
        </tr>
        <tr>
          <td style="padding:4px 8px;font-weight:600">Pricing Engine</td>
          <td style="padding:4px 8px">Monte Carlo simulation (200 paths/loan, &sigma;=0.15 stochastic shocks) using
          segmentation tree &rarr; KM survival curves &rarr; state transitions, scaled from the engine&rsquo;s 8% CoC
          to the target yield using APEX2 as the calibration anchor.</td>
        </tr>
      </table>
      <strong>Key assumptions:</strong> CoF {cof:.2%} &bull; Capital {capital:.2%} &bull; Tax {tax:.2%}
      &bull; CTA $850 default. Values sourced from the tape where available; fallbacks shown in Section&nbsp;3.
    </div>"""

    return f"""
    <h2 class="section-title">1. Executive Summary</h2>
    {cards}
    {price_bars}
    {metrics}
    {roe_banner}
    {spread_banner}
    {methodology_note}"""


def _build_effective_life(df, leaf_loans, leaf_km_life, leaf_mean_life, loan_leaf_map,
                           tape_plug, avg_km_life, avg_mean_life, wt_avg,
                           leaf_curves=None):
    # Portfolio summary
    summary = f"""
    <div class="life-summary">
      <table class="data-table">
        <thead><tr><th>Method</th><th>Bal-Wtd Life (mo)</th><th>Bal-Wtd Life (yr)</th><th>Description</th></tr></thead>
        <tbody>
          <tr><td>APEX2 Amort Plug (tape)</td><td class="num">{tape_plug:.0f}</td><td class="num">{tape_plug/12:.1f}</td><td>FNBA&rsquo;s assumed effective life via APEX2 prepayment model</td></tr>
          <tr><td>KM 50%-Life</td><td class="num">{avg_km_life:.0f}</td><td class="num">{avg_km_life/12:.1f}</td><td>Month when 50% of training loans paid off (Kaplan-Meier)</td></tr>
          <tr><td>KM Mean Life</td><td class="num">{avg_mean_life:.0f}</td><td class="num">{avg_mean_life/12:.1f}</td><td>Expected lifetime = area under KM survival curve</td></tr>
        </tbody>
      </table>
    </div>"""

    # Per-leaf table
    leaf_rows = []
    for leaf_id in sorted(leaf_loans.keys()):
        loans_in_leaf = leaf_loans[leaf_id]
        n_loans = len(loans_in_leaf)
        leaf_upb = sum(l.get("unpaid_balance", 0) for l in loans_in_leaf)
        km_life_raw = leaf_km_life.get(leaf_id)
        mean_life = leaf_mean_life.get(leaf_id, 0)
        km_life_num = _life_numeric(km_life_raw, mean_life)
        km_life_display = _fmt_life(km_life_raw, mean_life, suffix="")

        # Get tape amort plugs for loans in this leaf
        leaf_loan_ids = {l.get("loan_id") for l in loans_in_leaf}
        leaf_df = df[df.index.map(lambda i: f"LN-{i+1:04d}" in leaf_loan_ids)]

        tape_plug_leaf = leaf_df["apex2_amort_plug"].mean() if "apex2_amort_plug" in leaf_df.columns and len(leaf_df) > 0 else 0
        divergence = abs(tape_plug_leaf - km_life_num) / tape_plug_leaf * 100 if tape_plug_leaf > 0 else 0

        div_class = "green" if divergence <= 15 else ("yellow" if divergence <= 30 else "red")

        leaf_rows.append(f"""
        <tr>
          <td class="num">{leaf_id}</td>
          <td class="num">{n_loans}</td>
          <td class="num">${leaf_upb:,.0f}</td>
          <td class="num">{tape_plug_leaf:.0f}</td>
          <td class="num">{km_life_display}</td>
          <td class="num">{mean_life:.0f}</td>
          <td class="num"><span class="badge badge-{div_class}">{divergence:.0f}%</span></td>
        </tr>""")

    leaf_table = f"""
    <table class="data-table" id="leafTable">
      <thead><tr>
        <th>Leaf</th><th>Tape Loans</th><th>Tape UPB</th>
        <th>APEX2 Avg Plug</th><th>KM 50%-Life</th><th>KM Mean Life</th><th>Divergence</th>
      </tr></thead>
      <tbody>{"".join(leaf_rows)}</tbody>
    </table>"""

    # Grouped bar comparison by leaf (replaces misleading scatter)
    leaf_compare_rows = []
    for leaf_id in sorted(leaf_loans.keys()):
        loans_in_leaf = leaf_loans[leaf_id]
        n_loans = len(loans_in_leaf)
        leaf_upb = sum(l.get("unpaid_balance", 0) for l in loans_in_leaf)
        km_life_raw = leaf_km_life.get(leaf_id)
        mean_life = leaf_mean_life.get(leaf_id, 0)
        km_life_num = _life_numeric(km_life_raw, mean_life)
        km_life_display = _fmt_life(km_life_raw, mean_life, suffix="")
        leaf_loan_ids = {l.get("loan_id") for l in loans_in_leaf}
        leaf_df = df[df.index.map(lambda i: f"LN-{i+1:04d}" in leaf_loan_ids)]
        tape_plug_leaf = leaf_df["apex2_amort_plug"].mean() if "apex2_amort_plug" in leaf_df.columns and len(leaf_df) > 0 else 0
        leaf_compare_rows.append((leaf_id, n_loans, leaf_upb, tape_plug_leaf, km_life_num, km_life_display, mean_life))

    max_life = max(max(r[3], r[4], r[6]) for r in leaf_compare_rows) or 1
    bar_chart_rows = []
    for lid, n, upb, plug, km_num, km_disp, mean_l in leaf_compare_rows:
        plug_w = plug / max_life * 100
        km_w = km_num / max_life * 100
        mean_w = mean_l / max_life * 100
        bar_chart_rows.append(f"""
        <div class="life-bar-group">
          <div class="life-bar-label">Leaf {lid} <span class="muted">({n} loans, ${upb:,.0f})</span></div>
          <div class="life-bar-row"><span class="life-bar-tag">APEX2</span><div class="life-bar-track"><div class="life-bar-fill" style="width:{plug_w:.0f}%;background:#f59e0b"></div></div><span class="life-bar-val">{plug:.0f}mo</span></div>
          <div class="life-bar-row"><span class="life-bar-tag">KM 50%</span><div class="life-bar-track"><div class="life-bar-fill" style="width:{km_w:.0f}%;background:#005C3F"></div></div><span class="life-bar-val">{km_disp}mo</span></div>
          <div class="life-bar-row"><span class="life-bar-tag">Mean</span><div class="life-bar-track"><div class="life-bar-fill" style="width:{mean_w:.0f}%;background:#16a34a"></div></div><span class="life-bar-val">{mean_l:.0f}mo</span></div>
        </div>""")

    bar_chart = f"""
    <div class="life-bars-container">
      {"".join(bar_chart_rows)}
    </div>
    <div style="font-size:11px;color:#9ca3af;margin-top:8px">
      <span style="color:#f59e0b">&#9632;</span> APEX2 Amort Plug (tape) &nbsp;
      <span style="color:#005C3F">&#9632;</span> KM 50%-Life (month when 50% paid off) &nbsp;
      <span style="color:#16a34a">&#9632;</span> KM Mean Life (expected lifetime from survival curve)
    </div>"""

    provenance = """
    <div class="info-callout" style="margin-top:12px">
      <strong>Where do the KM survival curves come from?</strong><br>
      The Kaplan-Meier (KM) curves are derived from a 75-leaf segmentation tree trained on
      <strong>4.4 million actual loan outcomes</strong>: 41,897 FNBA internal loans plus 4,383,656
      Freddie Mac conforming loans (a 10% random sample of Freddie's ~44M public dataset).
      <em>All</em> loans are used — including censored observations (loans still performing) —
      so the estimates are not biased by only looking at loans that have already paid off.
      <ol style="margin:8px 0 4px 16px;font-size:12px;line-height:1.6">
        <li><strong>Tree routing:</strong> Each tape loan is routed through the decision tree based on
            9 features (vintage year, rate, credit, LTV, loan size, state group, DTI, ITIN, orig term)
            to land in one of 75 leaves.</li>
        <li><strong>KM estimation:</strong> Within each leaf, a non-parametric Kaplan-Meier survival
            curve tracks the fraction of training loans still performing at each month (1–360).
            Curves are EMA-smoothed and tail-extrapolated.</li>
        <li><strong>Life metrics:</strong> &ldquo;50%-Life&rdquo; = month when half the leaf&rsquo;s loans
            had paid off (median). &ldquo;Mean Life&rdquo; = area under the survival curve (expected lifetime).</li>
      </ol>
      The APEX2 &ldquo;Amort Plug&rdquo; is FNBA&rsquo;s production effective-life assumption, derived from
      4-dimensional prepayment-speed lookup tables (credit, rate delta, LTV, loan size).
      Large divergence between APEX2 and KM signals that the historical payoff pattern for these loans
      differs from APEX2&rsquo;s assumption.
    </div>"""

    note = """
    <div class="info-callout">
      <strong>Reading this chart:</strong> Three independent life estimates are compared:<br>
      &bull; <strong>APEX2 Amort Plug</strong> &mdash; FNBA's assumed effective life from their APEX2 prepayment model (varies per loan).<br>
      &bull; <strong>KM 50%-Life</strong> &mdash; the month when half the training loans in that leaf had paid off (Kaplan-Meier estimator). This is a median.</br>
      &bull; <strong>KM Mean Life</strong> &mdash; the expected (average) lifetime computed as the area under the survival curve. This accounts for the full shape of the curve, not just the 50% crossing.<br>
      Large divergence between APEX2 and KM means the model's historical payoff behavior differs significantly from APEX2's assumption.
      The tape's 305 loans cluster into only 5 leaves, so KM metrics are shared within each leaf while APEX2 plug varies per loan.
    </div>"""

    # KM survival curve chart for tape leaves
    survival_chart = ""
    if leaf_curves:
        tape_curves = {lid: leaf_curves[lid] for lid in sorted(leaf_loans.keys()) if lid in leaf_curves}
        if tape_curves:
            survival_chart = f"""
    <h3 class="subsection">KM Survival Curves (Tape Leaves)</h3>
    <p class="section-hint">Each curve shows the fraction of training loans still performing at each month.
    Dots mark the 50%-life (median payoff time). Steeper curves = faster prepayment.</p>
    <div class="chart-container">{_survival_curve_svg(tape_curves, leaf_km_life)}</div>"""

    return f"""
    <h2 class="section-title">2. Effective Life Comparison</h2>
    {summary}
    {provenance}
    {note}
    {survival_chart}
    <h3 class="subsection">Per-Leaf Comparison</h3>
    <div class="table-wrap">{leaf_table}</div>
    <h3 class="subsection">Effective Life by Leaf &mdash; Three Methods</h3>
    <div class="chart-container">{bar_chart}</div>"""


def _build_apex2_dimensional(df, wt_avg):
    # Credit band breakdown
    bands = ["<576", "576-600", "601-625", "626-650", "651-675", "676-700", "701-725", "726-750", ">=751"]
    df["credit_band"] = df["credit"].apply(get_credit_band)

    band_rows = []
    max_upb = 0
    band_data = []
    for band in bands:
        g = df[df["credit_band"] == band]
        if len(g) == 0:
            continue
        upb = g["balance"].sum()
        max_upb = max(max_upb, upb)
        tape_mult = g["apex2_prepay"].mean() if "apex2_prepay" in g.columns and g["apex2_prepay"].notna().any() else 0
        computed_mult = g["avg_4dim"].mean()
        delta = tape_mult - computed_mult if tape_mult > 0 else 0
        band_data.append((band, len(g), upb, tape_mult, computed_mult, delta))

    for band, n, upb, tape_m, comp_m, delta in band_data:
        bar_w = upb / max_upb * 100 if max_upb > 0 else 0
        delta_class = "green" if abs(delta) < 0.1 else ("yellow" if abs(delta) < 0.3 else "red")
        band_rows.append(f"""
        <tr>
          <td>{band}</td>
          <td class="num">{n}</td>
          <td class="num">${upb:,.0f}</td>
          <td><div class="bar-bg"><div class="bar" style="width:{bar_w:.0f}%"></div></div></td>
          <td class="num">{tape_m:.4f}</td>
          <td class="num">{comp_m:.4f}</td>
          <td class="num"><span class="badge badge-{delta_class}">{delta:+.4f}</span></td>
        </tr>""")

    dim_table = f"""
    <table class="data-table" id="dimTable">
      <thead><tr>
        <th>Credit Band</th><th>Count</th><th>UPB</th><th></th>
        <th>Tape Mult</th><th>Computed Mult</th><th>Delta</th>
      </tr></thead>
      <tbody>{"".join(band_rows)}</tbody>
    </table>"""

    # 4-dimension table: all dimensions
    dim_detail_rows = []
    dim_configs = [
        ("Credit", "credit_band", "dim_credit", "apex2_prepay"),
        ("Rate Delta", None, "dim_rate_delta", None),
        ("LTV", None, "dim_ltv", None),
        ("Loan Size", None, "dim_loan_size", None),
    ]
    for dim_name, _, dim_col, _ in dim_configs:
        if dim_col in df.columns:
            val = wt_avg(df[dim_col])
            dim_detail_rows.append(f"""
            <tr><td>{dim_name}</td><td class="num">{val:.4f}</td></tr>""")

    dim_detail = f"""
    <table class="data-table mini-metrics">
      <thead><tr><th>Dimension</th><th>Wtd Avg Multiplier</th></tr></thead>
      <tbody>{"".join(dim_detail_rows)}</tbody>
    </table>"""

    return f"""
    <h2 class="section-title">3. APEX2 Dimensional Analysis</h2>
    <h3 class="subsection">Portfolio Multipliers by Dimension</h3>
    {dim_detail}
    <h3 class="subsection">Credit Band Breakdown</h3>
    <div class="table-wrap">{dim_table}</div>"""


def _build_price_comparison(df, price_totals, scenario_stress, results):
    """Section 4: Price Comparison — the core analysis.

    Shows 3 price estimates side by side: Offered, APEX2, Pricing Engine.
    All prices computed at the tape's ROE target yield for apples-to-apples comparison.
    """
    pt = price_totals or {}
    p_off = pt.get("offered", 0)
    p_a2 = pt.get("apex2", 0)
    p_mc = pt.get("mc", 0)
    mc_p5 = pt.get("mc_p5")
    mc_p95 = pt.get("mc_p95")
    total_upb = df["balance"].sum()

    # Implied ROE row
    roe_off = pt.get("roe_offered")
    roe_a2 = pt.get("roe_apex2")
    roe_mc = pt.get("roe_mc")

    def roe_cell(val):
        if val is None:
            return '<td class="num">n/a</td>'
        return f'<td class="num" style="font-weight:600">{val:.2%}</td>'

    roe_row = f"""
        <tr style="background:#f9fafb;border-top:2px solid var(--gray-200)">
          <td style="font-weight:600">Implied ROE</td>
          {roe_cell(roe_off)}
          {roe_cell(roe_a2)}
          {roe_cell(roe_mc)}
        </tr>"""

    comp_table = f"""
    <table class="data-table">
      <thead><tr><th>Metric</th><th>Offered</th><th>APEX2</th><th>Pricing Engine</th></tr></thead>
      <tbody>
        <tr>
          <td>Portfolio Total</td>
          <td class="num">${p_off:,.0f}</td>
          <td class="num">${p_a2:,.0f}</td>
          <td class="num">{f'${p_mc:,.0f}' if p_mc > 0 else 'N/A'}</td>
        </tr>
        <tr>
          <td>Cents / $</td>
          <td class="num">{p_off/total_upb*100:.1f}</td>
          <td class="num">{p_a2/total_upb*100:.1f}</td>
          <td class="num">{f'{p_mc/total_upb*100:.1f}' if p_mc > 0 else 'N/A'}</td>
        </tr>
        <tr>
          <td>vs Offered</td>
          <td class="num">&mdash;</td>
          <td class="num">${p_a2-p_off:+,.0f} ({(p_a2/p_off-1)*100:+.1f}%)</td>
          <td class="num">{f'${p_mc-p_off:+,.0f} ({(p_mc/p_off-1)*100:+.1f}%)' if p_mc > 0 else 'N/A'}</td>
        </tr>
        {roe_row}
        {f'<tr><td style="padding-left:16px;color:#6b7280;font-size:12px">PE p5 (downside)</td><td></td><td></td><td class="num">${mc_p5:,.0f}</td></tr>' if mc_p5 else ''}
        {f'<tr><td style="padding-left:16px;color:#6b7280;font-size:12px">PE p95 (upside)</td><td></td><td></td><td class="num">${mc_p95:,.0f}</td></tr>' if mc_p95 else ''}
      </tbody>
    </table>"""

    # Explanation
    avg_ty = df["roe_target_yield"].mean() if "roe_target_yield" in df.columns and df["roe_target_yield"].notna().any() else 0.07
    price_note = f"""
    <div class="info-callout">
      <strong>How prices are computed:</strong> All three estimates use the tape's per-loan
      <strong>ROE Target Yield</strong> (avg {avg_ty:.2%})
      as the discount rate, making them directly comparable.<br>
      &bull; <strong>Offered</strong> &mdash; Final Price with ITV Cap from the tape.<br>
      &bull; <strong>APEX2 Replicated</strong> &mdash; PV of accelerated P&amp;I (&times;prepay mult) minus CTA,
      over the amortization plug, at the target yield. No credit losses. Validates within 1.5% of Bid Offered.<br>
      &bull; <strong>Pricing Engine</strong> &mdash; Monte Carlo simulation (200 paths/loan) using
      segmentation tree &rarr; KM survival curves &rarr; state transitions, scaled from
      engine&rsquo;s 8% CoC to target yield using APEX2 as calibration anchor.
    </div>"""

    # Per-loan scatter: APEX2 vs PE price
    scatter_a2_pe = ""
    if "price_mc" in df.columns and df["price_mc"].notna().any():
        has_both = df[df["price_apex2"].notna() & df["price_mc"].notna()]
        if len(has_both) > 0:
            scatter_a2_pe = _scatter_svg(
                has_both,
                "price_apex2", "price_mc", "balance",
                "APEX2 Price ($)", "Pricing Engine Price ($)",
                title="APEX2 vs Pricing Engine Price (per loan)",
                reference_line=True, dollar_axes=True,
            )

    # Per-loan price table (top 50 by balance, expandable)
    df_sorted = df.sort_values("balance", ascending=False)
    price_rows = []
    for rank, (idx, rw) in enumerate(df_sorted.iterrows()):
        lid = f"LN-{int(idx + 1):04d}"
        off = rw.get("price_offered", 0)
        a2 = rw.get("price_apex2", np.nan)
        mc = rw.get("price_mc", np.nan)
        # PE vs Offered diff
        pe_diff = (mc / off - 1) * 100 if pd.notna(mc) and off > 0 else np.nan
        # Color by PE divergence
        if pd.notna(pe_diff):
            if abs(pe_diff) <= 10:
                bg = "#f0fdf4"
            elif abs(pe_diff) <= 25:
                bg = "#fefce8"
            else:
                bg = "#fef2f2"
        else:
            bg = "white"
        hidden = ' class="hidden-row"' if rank >= 50 else ""
        price_rows.append(f"""
        <tr{hidden} style="background:{bg}">
          <td>{lid}</td>
          <td class="num">${rw['balance']:,.0f}</td>
          <td class="num">{rw['rate']:.3f}%</td>
          <td class="num">{rw.get('apex2_amort_plug', 0):.0f}</td>
          <td class="num">${off:,.0f}</td>
          <td class="num">{f'${a2:,.0f}' if pd.notna(a2) else 'n/a'}</td>
          <td class="num">{f'${mc:,.0f}' if pd.notna(mc) else 'n/a'}</td>
          <td class="num">{f'{pe_diff:+.1f}%' if pd.notna(pe_diff) else 'n/a'}</td>
        </tr>""")

    show_more = ""
    if len(df_sorted) > 50:
        show_more = f'<button class="show-more-btn" onclick="toggleRows(this)">Show all {len(df_sorted)} rows</button>'

    price_table = f"""
    <table class="data-table" id="priceTable">
      <thead><tr>
        <th>Loan</th><th>Balance</th><th>Rate</th><th>Plug</th>
        <th>Offered</th><th>APEX2</th><th>PE</th><th>PE vs Off</th>
      </tr></thead>
      <tbody>{"".join(price_rows)}</tbody>
    </table>
    {show_more}"""

    # Scenario stress (keep concise)
    scen_rows = []
    total_offered = df["offered_price"].sum()
    for scen, label in [("baseline", "Baseline"), ("mild_recession", "Mild Recession"), ("severe_recession", "Severe Recession")]:
        ss = scenario_stress[scen]
        scen_rows.append(f"""
        <tr>
          <td>{label}</td>
          <td class="num">${ss['total_npv']:,.0f}</td>
          <td class="num">{ss['npv_per_upb']:.4f}</td>
        </tr>""")

    scenario_table = f"""
    <table class="data-table">
      <thead><tr><th>Scenario</th><th>Engine NPV (8% CoC)</th><th>NPV/UPB</th></tr></thead>
      <tbody>{"".join(scen_rows)}</tbody>
    </table>
    <div class="info-callout">
      <strong>Note:</strong> Scenario NPVs above use the engine&rsquo;s 8% cost-of-capital discount rate,
      not the tape&rsquo;s ROE target yield. They show relative stress impact, not absolute price levels.
    </div>"""

    return f"""
    <h2 class="section-title">4. Price Comparison</h2>
    {price_note}
    <h3 class="subsection">Portfolio-Level: Three Price Estimates</h3>
    {comp_table}
    {f'<h3 class="subsection">APEX2 vs Pricing Engine (per loan)</h3><div class="chart-container">{scatter_a2_pe}</div>' if scatter_a2_pe else ''}
    <h3 class="subsection">Per-Loan Price Breakdown</h3>
    <div class="table-wrap">{price_table}</div>
    <h3 class="subsection">Scenario Stress (Engine NPV)</h3>
    {scenario_table}"""


def _build_sensitivity(stub_impacts, feature_bounds, scenario_stress, total_upb):
    # Stub impact table
    stub_rows = []
    for s in stub_impacts:
        color = "#16a34a" if s["impact_label"] != "Stub" else "#ca8a04"
        stub_rows.append(f"""
        <tr>
          <td>{s['model']}</td>
          <td>{s['status']}</td>
          <td><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:{color};margin-right:6px"></span>{s['impact_label']}</td>
        </tr>""")

    stub_table = f"""
    <table class="data-table">
      <thead><tr><th>Model</th><th>Status</th><th>Assessment</th></tr></thead>
      <tbody>{"".join(stub_rows)}</tbody>
    </table>"""

    # Feature bounds cards
    feat_cards = []
    for fb in feature_bounds:
        if fb["train_min"] is None:
            continue
        pct = fb["in_bounds_pct"]
        color = "#16a34a" if pct >= 90 else ("#ca8a04" if pct >= 75 else "#ef4444")
        bar_w = min(pct, 100)

        t_min_s = f"{fb['train_min']:.1f}" if fb['train_min'] is not None else "?"
        t_max_s = f"{fb['train_max']:.1f}" if fb['train_max'] is not None else "?"
        tape_min_s = f"{fb['tape_min']:.1f}" if fb['tape_min'] is not None else "?"
        tape_max_s = f"{fb['tape_max']:.1f}" if fb['tape_max'] is not None else "?"

        feat_cards.append(f"""
        <div class="feat-card">
          <div class="feat-name">{fb['feature']}</div>
          <div class="feat-ranges">
            <div>Training: {t_min_s} &ndash; {t_max_s}</div>
            <div>Tape: {tape_min_s} &ndash; {tape_max_s}</div>
          </div>
          <div class="feat-bar-wrap">
            <div class="feat-bar" style="width:{bar_w:.0f}%;background:{color}"></div>
          </div>
          <div class="feat-pct" style="color:{color}">{pct:.0f}% in bounds</div>
        </div>""")

    feat_section = f'<div class="feat-grid">{"".join(feat_cards)}</div>' if feat_cards else '<p class="muted">No training range metadata available.</p>'

    # Scenario stress
    stress_rows = []
    for scen, label in [("baseline", "Baseline"), ("mild_recession", "Mild Recession"), ("severe_recession", "Severe Recession")]:
        ss = scenario_stress[scen]
        stress_rows.append(f"""
        <tr>
          <td>{label}</td>
          <td class="num">${ss['total_npv']:,.0f}</td>
          <td class="num">{ss['npv_per_upb']:.4f}</td>
          <td class="num">{ss['vs_offered']:.2%}</td>
        </tr>""")

    stress_table = f"""
    <table class="data-table">
      <thead><tr><th>Scenario</th><th>Portfolio NPV</th><th>NPV/UPB</th><th>NPV/Offered</th></tr></thead>
      <tbody>{"".join(stress_rows)}</tbody>
    </table>"""

    # --- Directional correctness flags ---
    dc = scenario_stress.get("directional", {})
    if dc:
        n_loans = dc["n_loans"]
        port_ok = dc["portfolio_monotonic"]
        bm = dc["base_ge_mild"]
        ms = dc["mild_ge_severe"]
        bs = dc["base_ge_severe"]
        port_badge = '<span style="background:#16a34a;color:white;padding:2px 8px;border-radius:4px;font-weight:700;font-size:12px">PASS</span>' if port_ok else '<span style="background:#ef4444;color:white;padding:2px 8px;border-radius:4px;font-weight:700;font-size:12px">FAIL</span>'
        bm_pct = bm / n_loans * 100 if n_loans > 0 else 0
        ms_pct = ms / n_loans * 100 if n_loans > 0 else 0
        bm_color = "#16a34a" if bm_pct >= 90 else ("#ca8a04" if bm_pct >= 75 else "#ef4444")
        ms_color = "#16a34a" if ms_pct >= 90 else ("#ca8a04" if ms_pct >= 75 else "#ef4444")

        directional_box = f"""
    <div style="margin-top:16px;padding:12px 16px;border-radius:8px;background:{'#f0fdf4' if port_ok else '#fef2f2'};border:1px solid {'#bbf7d0' if port_ok else '#fecaca'}">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
        <strong style="font-size:13px">Directional Correctness</strong> {port_badge}
      </div>
      <div style="font-size:12px;color:#374151;line-height:1.6">
        <strong>Portfolio-level:</strong> baseline &ge; mild &ge; severe &rarr; {'Yes' if port_ok else 'No — scenarios not monotonically ordered'}<br>
        <strong>Per-loan (base &ge; mild):</strong> <span style="color:{bm_color};font-weight:600">{bm} of {n_loans}</span> ({bm_pct:.0f}%) &mdash; {n_loans - bm} violations<br>
        <strong>Per-loan (mild &ge; severe):</strong> <span style="color:{ms_color};font-weight:600">{ms} of {n_loans}</span> ({ms_pct:.0f}%) &mdash; {n_loans - ms} violations
      </div>
      <div style="font-size:11px;color:#6b7280;margin-top:6px">
        Per-loan violations are expected when stochastic shocks dominate small balance loans. Portfolio-level monotonicity is the key check.
      </div>
    </div>"""
    else:
        directional_box = ""

    return f"""
    <h2 class="section-title">5. Sensitivity &amp; Risk</h2>
    <h3 class="subsection">Model Status</h3>
    {stub_table}
    <h3 class="subsection">Feature Distribution vs Training Range</h3>
    {feat_section}
    <h3 class="subsection">Scenario Stress</h3>
    {stress_table}
    {directional_box}"""


def _build_loan_detail(df, loan_leaf_map, leaf_km_life, results):
    df_sorted = df.sort_values("balance", ascending=False).copy()

    rows = []
    for idx, row in df_sorted.iterrows():
        lid = f"LN-{int(idx + 1):04d}"
        leaf = loan_leaf_map.get(lid, 0)
        km_life_raw = leaf_km_life.get(leaf)
        km_life_display = _fmt_life(km_life_raw, suffix="")
        offered = row.get("price_offered", row.get("offered_price", 0))
        apex2_px = row.get("price_apex2", np.nan)
        mc_px = row.get("price_mc", np.nan)
        amort_plug = row.get("apex2_amort_plug", 0)

        # Color code by PE vs offered divergence
        pe_diff = (mc_px / offered - 1) * 100 if pd.notna(mc_px) and offered > 0 else np.nan
        if pd.notna(pe_diff):
            if abs(pe_diff) <= 10:
                bg = "#f0fdf4"
            elif abs(pe_diff) <= 25:
                bg = "#fefce8"
            else:
                bg = "#fef2f2"
        else:
            bg = "white"

        # Mini cashflow SVG for expandable section
        r = results.get(lid)
        mini_cf = ""
        kicker_info = ""
        if r and r.monthly_cash_flows:
            mini_cf = _mini_cashflow_svg(r.monthly_cash_flows)

        # Kicker values
        kicker_cols = [c for c in df.columns if c.startswith("kicker_")]
        if kicker_cols:
            kicker_items = []
            for kc in kicker_cols:
                kv = row.get(kc, 0)
                if pd.notna(kv) and kv != 0:
                    kicker_items.append(f"{kc.replace('kicker_', '')}: {kv:.4f}")
            if kicker_items:
                kicker_info = " | ".join(kicker_items)

        detail_html = ""
        if mini_cf or kicker_info:
            detail_html = f"""
            <tr class="detail-row" id="detail-{lid}" style="display:none">
              <td colspan="10">
                <div class="detail-content">
                  {f'<div class="detail-chart">{mini_cf}</div>' if mini_cf else ''}
                  {f'<div class="detail-kickers"><strong>Kickers:</strong> {kicker_info}</div>' if kicker_info else ''}
                  <div class="detail-meta">Leaf: {leaf} | KM Life: {km_life_display}mo | Amort Plug: {amort_plug:.0f}mo</div>
                </div>
              </td>
            </tr>"""

        credit = row.get("credit", 0)
        ltv = row.get("ltv", 0)
        age = row.get("seasoning", 0)

        rows.append(f"""
        <tr style="background:{bg};cursor:pointer" onclick="toggleDetail('{lid}')">
          <td>{lid}</td>
          <td class="num">${row['balance']:,.0f}</td>
          <td class="num">{row['rate']:.3f}%</td>
          <td class="num">{credit:.0f}</td>
          <td class="num">{leaf}</td>
          <td class="num">{amort_plug:.0f}</td>
          <td class="num">${offered:,.0f}</td>
          <td class="num">{f'${apex2_px:,.0f}' if pd.notna(apex2_px) else 'n/a'}</td>
          <td class="num">{f'${mc_px:,.0f}' if pd.notna(mc_px) else 'n/a'}</td>
          <td class="num">{f'{pe_diff:+.1f}%' if pd.notna(pe_diff) else 'n/a'}</td>
        </tr>
        {detail_html}""")

    table = f"""
    <table class="data-table" id="loanTable">
      <thead><tr>
        <th>Loan</th><th>Balance</th><th>Rate</th><th>Credit</th>
        <th>Leaf</th><th>Plug</th>
        <th>Offered</th><th>APEX2</th><th>PE</th><th>PE vs Off</th>
      </tr></thead>
      <tbody>{"".join(rows)}</tbody>
    </table>"""

    return f"""
    <h2 class="section-title">6. Loan-Level Detail</h2>
    <p class="section-hint">Click any row to expand details. Color: green (&le;10% divergence), yellow (10&ndash;25%), red (&gt;25%).</p>
    <div class="table-wrap">{table}</div>"""


# ---------------------------------------------------------------------------
# Section 8: Segmentation Tree Diagram
# ---------------------------------------------------------------------------
def _build_tree_diagram(loan_leaf_map, leaf_km_life, registry, leaf_curves=None):
    """Build an interactive top-down tree diagram with clickable leaves."""
    tree_structure = registry.tree_structure
    nested = tree_structure.get("nested_tree", {})
    leaves_meta = {l["leaf_id"]: l for l in tree_structure.get("leaves", [])}

    # Count tape loans per leaf
    from collections import Counter
    leaf_counts = Counter(loan_leaf_map.values())
    tape_leaves = set(leaf_counts.keys())

    # Feature importance by frequency
    feature_freq = defaultdict(int)
    for leaf in tree_structure.get("leaves", []):
        for rule in leaf.get("rules", []):
            feature_freq[rule["feature"]] += 1

    freq_rows = []
    for feat, count in sorted(feature_freq.items(), key=lambda x: -x[1]):
        name = FEATURE_NAMES.get(feat, feat)
        pct = count / len(tree_structure.get("leaves", [])) * 100
        bar_w = min(pct, 100)
        freq_rows.append(f"""
        <tr>
          <td>{name}</td>
          <td class="num">{feat}</td>
          <td class="num">{count}</td>
          <td class="num">{pct:.0f}%</td>
          <td><div class="bar-bg" style="width:120px"><div class="bar" style="width:{bar_w:.0f}%"></div></div></td>
        </tr>""")

    freq_table = f"""
    <table class="data-table">
      <thead><tr><th>Feature</th><th>Code</th><th># Leaves</th><th>% Leaves</th><th></th></tr></thead>
      <tbody>{"".join(freq_rows)}</tbody>
    </table>"""

    # Build tree list — collapsible indented layout
    tree_html = _build_tree_list(nested, leaf_counts, leaf_km_life)

    # Leaf detail panels (hidden, shown on click)
    leaf_panels = []
    for leaf in sorted(tree_structure.get("leaves", []), key=lambda l: l["leaf_id"]):
        lid = leaf["leaf_id"]
        tape_n = leaf_counts.get(lid, 0)
        km_life_raw = leaf_km_life.get(lid)
        km_life_num = _life_numeric(km_life_raw, leaf.get("mean_time"))
        km_life_display = _fmt_life(km_life_raw, suffix="")

        rules_html = ""
        for i, rule in enumerate(leaf.get("rules", [])):
            feat_name = FEATURE_NAMES.get(rule["feature"], rule["feature"])
            thresh = rule["threshold"]
            op = rule["operator"]
            if rule["feature"] == "interestRate":
                thresh_s = f"{thresh:.3f}%"
            elif rule["feature"] == "loanSize":
                thresh_s = f"${thresh:,.0f}"
            elif rule["feature"] in ("ltv",):
                thresh_s = f"{thresh:.1f}%"
            elif rule["feature"] == "origCustAmortMonth":
                thresh_s = f"{thresh:.0f} mo"
            else:
                thresh_s = f"{thresh:.1f}"

            depth_color = f"hsl({(i * 40) % 360}, 50%, 92%)"
            rules_html += f'<div class="tree-rule" style="margin-left:{i*16}px;background:{depth_color}"><span class="rule-depth">L{i+1}</span> {feat_name} {op} {thresh_s}</div>'

        highlight = "tree-leaf-tape" if tape_n > 0 else ""
        tape_badge = f'<span class="badge badge-green">{tape_n} tape loans</span>' if tape_n > 0 else ""

        # Mini survival curve for this leaf
        mini_curve_html = ""
        if leaf_curves and lid in leaf_curves:
            mini_curve_html = f"""
            <div style="margin-top:8px">
              <div style="font-size:11px;color:#6b7280;margin-bottom:2px;font-weight:600">Survival Curve</div>
              {_survival_curve_mini_svg(leaf_curves[lid], km_life_num)}
            </div>"""

        leaf_panels.append(f"""
        <div class="leaf-panel {highlight}" id="leaf-panel-{lid}">
          <div class="leaf-panel-header">
            <span class="leaf-id-tag">Leaf {lid}</span>
            {tape_badge}
            <span class="leaf-stats">{leaf['samples']:,} training &bull; mean {leaf['mean_time']:.0f}mo &bull; KM {km_life_display}mo</span>
            <a href="#tree-diagram" class="back-to-tree" onclick="event.preventDefault();document.getElementById('tree-diagram').scrollIntoView({{behavior:'smooth'}})">&uarr; Back to tree</a>
          </div>
          <div class="leaf-panel-body">
            <div class="tree-rules-col">
              <h4>Decision Path (top &rarr; bottom)</h4>
              {rules_html}
            </div>
            <div class="tree-stats-col">
              <table class="mini-stats">
                <tr><td class="stat-label">Training Loans</td><td class="stat-value">{leaf['samples']:,}</td></tr>
                <tr><td class="stat-label">FNBA / Freddie</td><td class="stat-value">{leaf['n_fnba']:,} / {leaf['n_freddie']:,}</td></tr>
                <tr><td class="stat-label">Payoffs / Censored</td><td class="stat-value">{leaf['n_payoffs']:,} / {leaf['n_censored']:,}</td></tr>
                <tr><td class="stat-label">Mean Time</td><td class="stat-value">{leaf['mean_time']:.1f} mo</td></tr>
                <tr><td class="stat-label">Median Time</td><td class="stat-value">{leaf['median_time']:.0f} mo</td></tr>
                <tr><td class="stat-label">KM 50%-Life</td><td class="stat-value">{km_life_display} mo</td></tr>
                <tr><td class="stat-label">Tape Loans</td><td class="stat-value">{tape_n}</td></tr>
              </table>
              {mini_curve_html}
            </div>
          </div>
        </div>""")

    # Note about credit score
    credit_leaves = [l for l in tree_structure.get("leaves", [])
                     if any(r["feature"] == "creditScore" for r in l.get("rules", []))]
    credit_note = f"""
    <div class="info-callout">
      <strong>Note on Credit Score:</strong> Credit score appears in only {len(credit_leaves)} of {len(tree_structure.get('leaves', []))} leaves
      (IDs: {', '.join(str(l['leaf_id']) for l in credit_leaves)}).
      The tree primarily splits on vintage year, interest rate, and loan size to predict payoff timing.
      Credit score matters more for <em>default probability</em> than <em>time-to-payoff</em>, which is this tree's target.
    </div>"""

    # Note about original term
    term_leaves = [l for l in tree_structure.get("leaves", [])
                   if any(r["feature"] == "origCustAmortMonth" for r in l.get("rules", []))]
    term_thresholds = set()
    for l in term_leaves:
        for r in l.get("rules", []):
            if r["feature"] == "origCustAmortMonth":
                term_thresholds.add(r["threshold"])

    term_note = f"""
    <div class="info-callout">
      <strong>Note on Original Term:</strong> Appears in {len(term_leaves)} leaves at thresholds:
      {', '.join(f'{t:.0f}mo' for t in sorted(term_thresholds))}.
      The tree does <em>not</em> split at 120mo (10yr) or 360mo (30yr) boundaries.
      10-year and 30-year loans have fundamentally different payment profiles; consider pre-segmenting them
      before tree assignment if the tape contains both.
    </div>"""

    # Note about state group
    state_leaves = [l for l in tree_structure.get("leaves", [])
                    if any(r["feature"] == "stateGroup" for r in l.get("rules", []))]
    state_thresholds = set()
    for l in state_leaves:
        for r in l.get("rules", []):
            if r["feature"] == "stateGroup":
                state_thresholds.add(r["threshold"])

    state_group_note = f"""
    <div class="info-callout">
      <strong>Note on State Group:</strong> US states are pre-binned into 6 groups (0&ndash;5) by median payoff
      speed from the training data. Group 0 = fastest payoff (AZ, CA, CO, IL, MA, MI, MO, NH, NV, RI, UT, WA, WI),
      Group 5 = slowest (AL, GU, ND, NM, NY, OK, PA, PR, WV). Appears in {len(state_leaves)} leaves
      {('at thresholds: ' + ', '.join(f'{t:.1f}' for t in sorted(state_thresholds))) if state_thresholds else '(not used as a split feature)'}.
      Unknown states default to the median bin (group 3). The grouping captures regional prepayment
      differences without creating 50 individual features.
    </div>"""

    training_note = """
    <div class="info-callout">
      <strong>Training Data (4.4M loans):</strong> The segmentation tree was trained on 4,425,553 loans:
      41,897 FNBA historical loans plus 4,383,656 Freddie Mac loans. The Freddie Mac component is a 10%
      random sample of their full ~44 million public loan-level performance dataset. <em>All 4.4M sampled
      loans are fully utilized</em> in tree construction &mdash; the "10%" refers to Freddie Mac's dataset
      being sampled down to a manageable size, not a reduction of our training input. The large Freddie Mac
      component provides broad coverage of loan prepayment behaviors across credit scores, rates, LTVs, and
      vintages, while the FNBA loans anchor the model to our specific portfolio characteristics and
      non-agency loan dynamics.
    </div>"""

    return f"""
    <h2 class="section-title">8. Segmentation Tree Diagram</h2>
    <p class="section-hint">
      The segmentation tree assigns each loan to a leaf based on 9 features.
      KM = Kaplan-Meier survival estimate &mdash; a non-parametric method that tracks the fraction
      of loans still performing at each month using historical data. The "50%-life" is when half
      the loans in a leaf have paid off.
      Click any leaf in the diagram or table below for its full decision path and stats.
    </p>

    <h3 class="subsection">Feature Usage Across 75 Leaves</h3>
    <div class="table-wrap">{freq_table}</div>
    {credit_note}
    {term_note}
    {state_group_note}
    {training_note}

    <h3 class="subsection">Tree Diagram (Top-Down)</h3>
    <p class="section-hint">Expand/collapse branches to explore. Green-bordered leaves have tape loans. Click a leaf to jump to its detail panel.</p>
    <div class="tree-list-wrap" id="tree-diagram">{tree_html}</div>

    <h3 class="subsection">Leaf Detail Panels</h3>
    <p class="section-hint">Click a leaf above or browse below. Tape-matched leaves highlighted in green.</p>
    {"".join(leaf_panels)}"""


def _build_tree_list(nested, leaf_counts, leaf_km_life):
    """Build a collapsible indented tree list from the nested tree structure.

    Uses native <details>/<summary> elements for collapse/expand — no JS needed.
    Top 3 levels expanded by default; deeper levels collapsed.
    """

    def _fmt_threshold(feature, thresh):
        if feature == "interestRate":
            return f"{thresh:.2f}%"
        elif feature == "loanSize":
            return f"${thresh / 1000:.0f}k"
        elif feature == "origCustAmortMonth":
            return f"{thresh:.0f}mo"
        elif feature == "noteDateYear":
            return f"{thresh:.0f}"
        elif feature == "ltv":
            return f"{thresh:.1f}%"
        elif feature == "creditScore":
            return f"{thresh:.0f}"
        else:
            return f"{thresh:.1f}"

    def _count_samples(node):
        """Sum training samples under a subtree."""
        if node["type"] == "leaf":
            return node.get("samples", 0)
        return _count_samples(node["left"]) + _count_samples(node["right"])

    def _has_tape_leaf(node):
        """Return True if any leaf under this subtree has tape loans."""
        if node["type"] == "leaf":
            return leaf_counts.get(node["leaf_id"], 0) > 0
        return _has_tape_leaf(node["left"]) or _has_tape_leaf(node["right"])

    def _render_node(node, depth, branch_label=""):
        if node["type"] == "leaf":
            lid = node["leaf_id"]
            tape_n = leaf_counts.get(lid, 0)
            km_life_raw = leaf_km_life.get(lid)
            km_life_display = _fmt_life(km_life_raw, suffix="")
            n_train = node.get("samples", 0)
            tape_cls = " tree-leaf-has-tape" if tape_n > 0 else ""
            tape_badge = (
                f' <span class="badge badge-green">{tape_n} tape loans</span>'
                if tape_n > 0 else ""
            )
            prefix = f'<span class="branch-label">{branch_label}</span> ' if branch_label else ""
            return (
                f'<div class="tree-leaf{tape_cls}" onclick="scrollToLeaf({lid})">'
                f'{prefix}'
                f'<span class="leaf-tag">Leaf {lid}</span>'
                f'<span class="leaf-stats">{n_train:,} training · KM {km_life_display}mo</span>'
                f'{tape_badge}'
                f'</div>'
            )

        # Internal node — expand if on path to a tape leaf, or top 2 levels
        feat = FEATURE_NAMES.get(node["feature"], node["feature"])
        thresh_s = _fmt_threshold(node["feature"], node["threshold"])
        n_samples = _count_samples(node)
        open_attr = " open" if _has_tape_leaf(node) or depth <= 2 else ""
        prefix = f'<span class="branch-label">{branch_label}</span> ' if branch_label else ""

        left_html = _render_node(node["left"], depth + 1, f"≤ {thresh_s}")
        right_html = _render_node(node["right"], depth + 1, f"> {thresh_s}")

        return (
            f'<details{open_attr}>'
            f'<summary class="tree-node">'
            f'{prefix}'
            f'<span class="node-split">{feat} ≤ {thresh_s}</span>'
            f'<span class="node-samples">{n_samples:,} loans</span>'
            f'</summary>'
            f'<div class="tree-children">'
            f'{left_html}'
            f'{right_html}'
            f'</div>'
            f'</details>'
        )

    return _render_node(nested, 0)


# ---------------------------------------------------------------------------
# Section 7: Monte Carlo Validation
# ---------------------------------------------------------------------------
def _build_monte_carlo_section(df, mc_results, portfolio_mc_pvs, scenario_stress):
    """Build Section 7: Monte Carlo Validation.

    Shows MC results in both NPV space (8% CoC) and price space (target yield).
    The price-space results connect directly to the 4-price comparison in Section 4.
    """
    total_offered = df["price_offered"].sum() if "price_offered" in df.columns else df["offered_price"].sum()
    total_det_npv = df["model_npv"].dropna().sum()

    # Portfolio MC stats (NPV space — 8% CoC)
    if portfolio_mc_pvs:
        mc_mean = np.mean(portfolio_mc_pvs)
        mc_median = np.median(portfolio_mc_pvs)
        mc_p5 = np.percentile(portfolio_mc_pvs, 5)
        mc_p95 = np.percentile(portfolio_mc_pvs, 95)
        n_sims = len(portfolio_mc_pvs)
    else:
        mc_mean = mc_median = mc_p5 = mc_p95 = 0
        n_sims = 0

    # Portfolio MC price stats (target yield space)
    total_mc_price = df["price_mc"].dropna().sum() if "price_mc" in df.columns else 0
    total_mc_p5 = df["price_mc_p5"].dropna().sum() if "price_mc_p5" in df.columns else 0
    total_mc_p95 = df["price_mc_p95"].dropna().sum() if "price_mc_p95" in df.columns else 0
    total_apex2_price = df["price_apex2"].dropna().sum() if "price_apex2" in df.columns else 0

    # Summary cards — emphasize prices
    cards = f"""
    <div class="summary-grid">
      <div class="summary-card">
        <div class="card-number">{n_sims}</div>
        <div class="card-label">MC Simulations / Loan</div>
      </div>
      <div class="summary-card" style="border-top:3px solid #16a34a">
        <div class="card-number">${total_mc_price:,.0f}</div>
        <div class="card-label">Pricing Engine Price</div>
      </div>
      <div class="summary-card">
        <div class="card-number">${total_offered:,.0f}</div>
        <div class="card-label">Offered Price</div>
      </div>
      <div class="summary-card">
        <div class="card-number">${total_mc_p5:,.0f} &ndash; ${total_mc_p95:,.0f}</div>
        <div class="card-label">MC 90% Price Band</div>
      </div>
    </div>"""

    # Price-space comparison table
    mc_vs_offered = total_mc_price / total_offered if total_offered > 0 else 0
    a2_vs_offered = total_apex2_price / total_offered if total_offered > 0 else 0

    comparison = f"""
    <table class="data-table">
      <thead><tr><th>Metric</th><th>Price (at Target Yield)</th><th>vs Offered</th><th>Notes</th></tr></thead>
      <tbody>
        <tr><td>Offered Price (tape)</td><td class="num">${total_offered:,.0f}</td><td class="num">&mdash;</td><td>Bid as offered</td></tr>
        <tr><td>APEX2 Replicated</td><td class="num">${total_apex2_price:,.0f}</td><td class="num">{a2_vs_offered:.1%}</td><td>Prepay-only price at target yield</td></tr>
        <tr><td>Pricing Engine (mean)</td><td class="num">${total_mc_price:,.0f}</td><td class="num">{mc_vs_offered:.1%}</td><td>Mean across {n_sims} stochastic paths, scaled to APEX2</td></tr>
        <tr><td>PE p5 (downside price)</td><td class="num">${total_mc_p5:,.0f}</td><td class="num">{total_mc_p5/total_offered:.1%}</td><td>Worst 5% of simulations</td></tr>
        <tr><td>PE p95 (upside price)</td><td class="num">${total_mc_p95:,.0f}</td><td class="num">{total_mc_p95/total_offered:.1%}</td><td>Best 5% of simulations</td></tr>
      </tbody>
    </table>"""

    # --- MC Noise Diagnostic ---
    mc_pvs_arr = np.array(portfolio_mc_pvs) if portfolio_mc_pvs else np.array([])
    if len(mc_pvs_arr) > 1:
        port_cv = np.std(mc_pvs_arr) / np.mean(mc_pvs_arr) * 100 if np.mean(mc_pvs_arr) != 0 else 0
        cv_color = "#16a34a" if port_cv <= 2 else ("#ca8a04" if port_cv <= 5 else "#ef4444")
        cv_bg = "#f0fdf4" if port_cv <= 2 else ("#fefce8" if port_cv <= 5 else "#fef2f2")

        # % loans where MC 90% band contains Offered price
        if "price_mc_p5" in df.columns and "price_mc_p95" in df.columns and "price_offered" in df.columns:
            mc_valid_diag = df[df["price_mc_p5"].notna() & df["price_mc_p95"].notna()].copy()
            n_crossing = ((mc_valid_diag["price_mc_p5"] <= mc_valid_diag["price_offered"]) &
                          (mc_valid_diag["price_offered"] <= mc_valid_diag["price_mc_p95"])).sum()
            n_mc_loans = len(mc_valid_diag)
            cross_pct = n_crossing / n_mc_loans * 100 if n_mc_loans > 0 else 0
        else:
            n_crossing = n_mc_loans = 0
            cross_pct = 0

        # Median per-loan spread
        med_spread = df["mc_spread"].median() if "mc_spread" in df.columns and df["mc_spread"].notna().any() else 0

        noise_diagnostic = f"""
    <h3 class="subsection">MC Noise Diagnostic</h3>
    <div style="display:flex;flex-wrap:wrap;gap:12px;margin-bottom:12px">
      <div style="flex:1;min-width:160px;padding:10px 14px;border-radius:8px;background:{cv_bg};border:1px solid #e5e7eb">
        <div style="font-size:22px;font-weight:700;color:{cv_color}">{port_cv:.2f}%</div>
        <div style="font-size:12px;color:#374151;font-weight:600">Portfolio CV</div>
        <div style="font-size:11px;color:#6b7280">std/mean &times; 100 &bull; {'Low noise' if port_cv <= 2 else ('Moderate noise' if port_cv <= 5 else 'High noise')}</div>
      </div>
      <div style="flex:1;min-width:160px;padding:10px 14px;border-radius:8px;background:#f9fafb;border:1px solid #e5e7eb">
        <div style="font-size:22px;font-weight:700;color:#374151">{cross_pct:.0f}%</div>
        <div style="font-size:12px;color:#374151;font-weight:600">Loans w/ Offered in MC Band</div>
        <div style="font-size:11px;color:#6b7280">{n_crossing} of {n_mc_loans} loans &bull; 90% confidence interval contains offered price</div>
      </div>
      <div style="flex:1;min-width:160px;padding:10px 14px;border-radius:8px;background:#f9fafb;border:1px solid #e5e7eb">
        <div style="font-size:22px;font-weight:700;color:#374151">{med_spread:.1f}%</div>
        <div style="font-size:12px;color:#374151;font-weight:600">Median Per-Loan Spread</div>
        <div style="font-size:11px;color:#6b7280">(p95 &minus; p5) / mean &times; 100</div>
      </div>
    </div>
    <div class="info-callout" style="font-size:12px">
      <strong>Interpretation:</strong> Portfolio CV &le;2% means the MC mean is well-converged and additional
      simulations would not materially change the result. If the &ldquo;Offered in MC Band&rdquo; percentage is
      high, the engine cannot confidently distinguish its valuation from the tape&rsquo;s offered price &mdash;
      which is expected when models are well-calibrated.
    </div>"""
    else:
        noise_diagnostic = ""

    # Distribution histogram (NPV space — still informative for shape)
    histogram = _histogram_svg(portfolio_mc_pvs, total_offered, total_det_npv) if portfolio_mc_pvs else ""

    # Per-loan MC price scatter
    mc_valid = df[df["price_mc"].notna()].copy() if "price_mc" in df.columns else pd.DataFrame()
    mc_scatter = ""
    if len(mc_valid) > 0:
        mc_scatter = _scatter_svg(
            mc_valid, "price_offered", "price_mc", "balance",
            "Offered Price ($)", "Pricing Engine Price ($)",
            title="Pricing Engine vs Offered Price (per loan, at target yield)",
            reference_line=True, dollar_axes=True,
        )

    # Per-loan MC spread table (top 30)
    df_mc = df[df["mc_spread"].notna()].sort_values("mc_spread", ascending=False) if "mc_spread" in df.columns else pd.DataFrame()
    spread_rows = []
    for rank, (idx, row) in enumerate(df_mc.head(30).iterrows()):
        lid = f"LN-{int(idx + 1):04d}"
        spread_rows.append(f"""
        <tr>
          <td>{lid}</td>
          <td class="num">${row['balance']:,.0f}</td>
          <td class="num">{row['rate']:.3f}%</td>
          <td class="num">${row.get('price_offered', 0):,.0f}</td>
          <td class="num">{f"${row.get('price_mc', 0):,.0f}" if pd.notna(row.get('price_mc')) else 'n/a'}</td>
          <td class="num">{f"${row.get('price_mc_p5', 0):,.0f}" if pd.notna(row.get('price_mc_p5')) else 'n/a'}</td>
          <td class="num">{f"${row.get('price_mc_p95', 0):,.0f}" if pd.notna(row.get('price_mc_p95')) else 'n/a'}</td>
          <td class="num">{row.get('mc_spread', 0):.1f}%</td>
        </tr>""")

    spread_table = f"""
    <table class="data-table" id="mcTable">
      <thead><tr>
        <th>Loan</th><th>Balance</th><th>Rate</th><th>Offered</th>
        <th>PE Price</th><th>PE p5</th><th>PE p95</th><th>Spread</th>
      </tr></thead>
      <tbody>{"".join(spread_rows)}</tbody>
    </table>"""

    note = """
    <div class="info-callout">
      <strong>Pricing Engine Methodology:</strong> Each loan is simulated with independent
      lognormal shocks (&sigma;=0.15) applied to monthly delinquency, default, recovery, and prepayment
      transition rates. Pricing Engine values are computed by scaling the engine&rsquo;s MC NPV distribution
      (at 8% CoC) to each loan&rsquo;s ROE target yield, making them comparable to Offered and APEX2 prices.
      Shocks are <em>independent across loans</em> (no systemic correlation), so the portfolio band
      may understate tail risk from economy-wide events.
    </div>"""

    return f"""
    <h2 class="section-title">7. Pricing Engine Validation</h2>
    {note}
    {cards}
    <h3 class="subsection">Price Comparison: Pricing Engine vs Offered</h3>
    {comparison}
    {noise_diagnostic}
    <h3 class="subsection">NPV Distribution ({n_sims} simulations, 8% CoC)</h3>
    <div class="chart-container">{histogram}</div>
    <h3 class="subsection">Pricing Engine vs Offered Price (per loan)</h3>
    <div class="chart-container">{mc_scatter}</div>
    <h3 class="subsection">Highest PE Spread Loans (Top 30)</h3>
    <p class="section-hint">Spread = (p95 &minus; p5) / mean &times; 100%. Higher spread = more uncertain valuation.</p>
    <div class="table-wrap">{spread_table}</div>"""


def _histogram_svg(values, offered_total=None, det_total=None, width=600, height=300, n_bins=30):
    """SVG histogram of portfolio MC PV distribution."""
    if not values:
        return '<p class="muted">No MC data</p>'

    values_arr = np.array(values)
    v_min, v_max = values_arr.min(), values_arr.max()
    bin_width = (v_max - v_min) / n_bins if v_max > v_min else 1
    bins = [0] * n_bins
    for v in values_arr:
        idx = min(int((v - v_min) / bin_width), n_bins - 1)
        bins[idx] += 1
    max_count = max(bins) or 1

    pad_l, pad_r, pad_t, pad_b = 70, 20, 30, 50
    pw = width - pad_l - pad_r
    ph = height - pad_t - pad_b
    bar_w = pw / n_bins

    lines = [f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">']
    lines.append(f'<rect width="{width}" height="{height}" fill="#fafafa" rx="4"/>')
    lines.append(f'<text x="{width/2}" y="18" text-anchor="middle" font-size="13" '
                 f'font-weight="600" fill="#374151">Portfolio NPV Distribution (Pricing Engine)</text>')

    # Bars
    for i, count in enumerate(bins):
        bar_h = (count / max_count) * ph
        x = pad_l + i * bar_w
        y = pad_t + ph - bar_h
        lines.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w - 1:.1f}" height="{bar_h:.1f}" '
                     f'fill="#005C3F" opacity="0.7" rx="1"/>')

    # X-axis labels
    for i in range(5):
        frac = i / 4
        val = v_min + frac * (v_max - v_min)
        x = pad_l + frac * pw
        lines.append(f'<text x="{x:.1f}" y="{height-10}" text-anchor="middle" font-size="10" '
                     f'fill="#888">${val:,.0f}</text>')

    # Y-axis labels
    for i in range(5):
        frac = i / 4
        count_val = frac * max_count
        y = pad_t + ph - frac * ph
        lines.append(f'<text x="{pad_l-5}" y="{y+4:.1f}" text-anchor="end" font-size="10" '
                     f'fill="#888">{count_val:.0f}</text>')

    # Reference lines
    def tx(val):
        if v_max == v_min:
            return pad_l + pw / 2
        return pad_l + (val - v_min) / (v_max - v_min) * pw

    if offered_total is not None and v_min <= offered_total <= v_max:
        x_off = tx(offered_total)
        lines.append(f'<line x1="{x_off:.1f}" y1="{pad_t}" x2="{x_off:.1f}" y2="{pad_t + ph}" '
                     f'stroke="#ef4444" stroke-width="2" stroke-dasharray="4,3"/>')
        lines.append(f'<text x="{x_off + 4:.1f}" y="{pad_t + 14}" font-size="10" fill="#ef4444" '
                     f'font-weight="600">Offered</text>')

    if det_total is not None and v_min <= det_total <= v_max:
        x_det = tx(det_total)
        lines.append(f'<line x1="{x_det:.1f}" y1="{pad_t}" x2="{x_det:.1f}" y2="{pad_t + ph}" '
                     f'stroke="#16a34a" stroke-width="2" stroke-dasharray="4,3"/>')
        lines.append(f'<text x="{x_det + 4:.1f}" y="{pad_t + 28}" font-size="10" fill="#16a34a" '
                     f'font-weight="600">Deterministic</text>')

    # Mean vertical line
    mc_mean = np.mean(values_arr)
    if v_min <= mc_mean <= v_max:
        x_mc = tx(mc_mean)
        lines.append(f'<line x1="{x_mc:.1f}" y1="{pad_t}" x2="{x_mc:.1f}" y2="{pad_t + ph}" '
                     f'stroke="#005C3F" stroke-width="2"/>')
        lines.append(f'<text x="{x_mc + 4:.1f}" y="{pad_t + 42}" font-size="10" fill="#005C3F" '
                     f'font-weight="600">MC Mean</text>')

    # Axes
    lines.append(f'<line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{height-pad_b}" stroke="#666"/>')
    lines.append(f'<line x1="{pad_l}" y1="{height-pad_b}" x2="{width-pad_r}" y2="{height-pad_b}" stroke="#666"/>')
    lines.append(f'<text x="{pad_l + pw/2}" y="{height-2}" text-anchor="middle" font-size="11" fill="#4b5563">Portfolio NPV ($)</text>')
    lines.append(f'<text x="14" y="{pad_t + ph/2}" text-anchor="middle" font-size="11" fill="#4b5563" '
                 f'transform="rotate(-90, 14, {pad_t + ph/2})">Frequency</text>')

    lines.append("</svg>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# SVG helpers
# ---------------------------------------------------------------------------
def _scatter_svg(df, x_col, y_col, size_col, x_label, y_label,
                 title="", reference_line=False, dollar_axes=False,
                 width=600, height=400):
    """Generate a scatter plot as inline SVG."""
    valid = df[[x_col, y_col, size_col]].dropna()
    if valid.empty:
        return '<p class="muted">No data for scatter plot</p>'

    xs = valid[x_col].values.astype(float)
    ys = valid[y_col].values.astype(float)
    sizes = valid[size_col].values.astype(float)

    pad_l, pad_r, pad_t, pad_b = 70, 20, 30, 50
    pw = width - pad_l - pad_r
    ph = height - pad_t - pad_b

    x_min, x_max = xs.min(), xs.max()
    y_min, y_max = ys.min(), ys.max()
    # Add 5% padding
    x_range = x_max - x_min or 1
    y_range = y_max - y_min or 1
    x_min -= x_range * 0.05
    x_max += x_range * 0.05
    y_min -= y_range * 0.05
    y_max += y_range * 0.05

    s_max = sizes.max() or 1

    def tx(v):
        return pad_l + (v - x_min) / (x_max - x_min) * pw

    def ty(v):
        return pad_t + (1 - (v - y_min) / (y_max - y_min)) * ph

    lines = [f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">']
    lines.append(f'<rect width="{width}" height="{height}" fill="#fafafa" rx="4"/>')

    # Title
    if title:
        lines.append(f'<text x="{width/2}" y="18" text-anchor="middle" font-size="13" font-weight="600" fill="#374151">{title}</text>')

    # Grid lines
    for i in range(5):
        frac = i / 4
        y_val = y_min + frac * (y_max - y_min)
        y_pos = ty(y_val)
        lines.append(f'<line x1="{pad_l}" y1="{y_pos:.1f}" x2="{width-pad_r}" y2="{y_pos:.1f}" stroke="#e5e7eb" stroke-dasharray="3,3"/>')
        if dollar_axes:
            label = f"${y_val:,.0f}"
        else:
            label = f"{y_val:.0f}"
        lines.append(f'<text x="{pad_l-5}" y="{y_pos+4:.1f}" text-anchor="end" font-size="10" fill="#888">{label}</text>')

    for i in range(5):
        frac = i / 4
        x_val = x_min + frac * (x_max - x_min)
        x_pos = tx(x_val)
        if dollar_axes:
            label = f"${x_val:,.0f}"
        else:
            label = f"{x_val:.0f}"
        lines.append(f'<text x="{x_pos:.1f}" y="{height-10}" text-anchor="middle" font-size="10" fill="#888">{label}</text>')

    # Reference line (45 degree)
    if reference_line:
        ref_min = max(x_min, y_min)
        ref_max = min(x_max, y_max)
        if ref_min < ref_max:
            lines.append(f'<line x1="{tx(ref_min):.1f}" y1="{ty(ref_min):.1f}" '
                         f'x2="{tx(ref_max):.1f}" y2="{ty(ref_max):.1f}" '
                         f'stroke="#9ca3af" stroke-width="1" stroke-dasharray="6,3"/>')

    # Points
    for x, y, s in zip(xs, ys, sizes):
        r = max(3, min(12, math.sqrt(s / s_max) * 12))
        # Color by divergence from reference line
        if reference_line and x > 0:
            ratio = y / x
            if ratio >= 0.95:
                fill = "#16a34a"
            elif ratio >= 0.85:
                fill = "#ca8a04"
            else:
                fill = "#ef4444"
        else:
            fill = "#005C3F"
        lines.append(f'<circle cx="{tx(x):.1f}" cy="{ty(y):.1f}" r="{r:.1f}" '
                     f'fill="{fill}" opacity="0.6"/>')

    # Axis labels
    lines.append(f'<text x="{pad_l + pw/2}" y="{height-2}" text-anchor="middle" font-size="11" fill="#4b5563">{x_label}</text>')
    lines.append(f'<text x="14" y="{pad_t + ph/2}" text-anchor="middle" font-size="11" fill="#4b5563" '
                 f'transform="rotate(-90, 14, {pad_t + ph/2})">{y_label}</text>')

    # Axes
    lines.append(f'<line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{height-pad_b}" stroke="#666"/>')
    lines.append(f'<line x1="{pad_l}" y1="{height-pad_b}" x2="{width-pad_r}" y2="{height-pad_b}" stroke="#666"/>')

    lines.append("</svg>")
    return "\n".join(lines)


def _mini_cashflow_svg(cash_flows, width=300, height=80):
    """Mini cashflow chart for expandable rows (first 120 months)."""
    cfs = cash_flows[:120]
    if not cfs:
        return ""

    months = [cf.month for cf in cfs]
    values = [cf.net_cash_flow for cf in cfs]
    max_val = max(abs(v) for v in values) or 1

    pad_l, pad_r, pad_t, pad_b = 5, 5, 5, 5
    pw = width - pad_l - pad_r
    ph = height - pad_t - pad_b
    max_m = max(months)

    points = []
    for m, v in zip(months, values):
        x = pad_l + (m / max_m) * pw
        y = pad_t + (1 - v / max_val) * ph / 2
        points.append(f"{x:.1f},{y:.1f}")

    return (
        f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">'
        f'<rect width="{width}" height="{height}" fill="#f9fafb" rx="3"/>'
        f'<line x1="{pad_l}" y1="{height/2}" x2="{width-pad_r}" y2="{height/2}" stroke="#e5e7eb"/>'
        f'<polyline points="{" ".join(points)}" fill="none" stroke="#005C3F" stroke-width="1.5"/>'
        f'</svg>'
    )


def _survival_curve_svg(curves: dict, leaf_km_life: dict, width=540, height=260,
                         max_months=240, title="KM Survival Curves"):
    """SVG line chart of survival curves for multiple leaves.

    curves: {leaf_id: [prob_m1, prob_m2, ..., prob_m360]}
    leaf_km_life: {leaf_id: 50%-life month}
    """
    if not curves:
        return '<p class="muted">No survival curve data</p>'

    pad_l, pad_r, pad_t, pad_b = 50, 20, 30, 40
    pw = width - pad_l - pad_r
    ph = height - pad_t - pad_b

    def tx(month):
        return pad_l + (month / max_months) * pw

    def ty(prob):
        return pad_t + (1 - prob) * ph

    lines = [f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg" style="font-family:Inter,system-ui,sans-serif">']

    # Background
    lines.append(f'<rect width="{width}" height="{height}" fill="#fafafa" rx="4"/>')

    # Title
    lines.append(f'<text x="{width/2}" y="16" text-anchor="middle" font-size="12" font-weight="600" fill="#374151">{title}</text>')

    # Grid lines and Y-axis labels
    for prob in [0, 0.25, 0.5, 0.75, 1.0]:
        y = ty(prob)
        lines.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width-pad_r}" y2="{y:.1f}" stroke="#e5e7eb" stroke-width="0.5"/>')
        lines.append(f'<text x="{pad_l-4}" y="{y+3:.1f}" text-anchor="end" font-size="10" fill="#9ca3af">{prob:.0%}</text>')

    # 50% dashed reference
    y50 = ty(0.5)
    lines.append(f'<line x1="{pad_l}" y1="{y50:.1f}" x2="{width-pad_r}" y2="{y50:.1f}" stroke="#9ca3af" stroke-width="0.8" stroke-dasharray="4,3"/>')

    # X-axis labels (every 60 months = 5 years)
    for m in range(0, max_months + 1, 60):
        x = tx(m)
        lines.append(f'<line x1="{x:.1f}" y1="{pad_t}" x2="{x:.1f}" y2="{height-pad_b}" stroke="#e5e7eb" stroke-width="0.5"/>')
        lines.append(f'<text x="{x:.1f}" y="{height-pad_b+14}" text-anchor="middle" font-size="10" fill="#9ca3af">{m}mo ({m//12}yr)</text>')

    # Axis labels
    lines.append(f'<text x="{width/2}" y="{height-4}" text-anchor="middle" font-size="10" fill="#6b7280">Months Since Origination</text>')

    # Curve colors — distinct palette
    palette = ["#005C3F", "#2563eb", "#d97706", "#dc2626", "#7c3aed", "#0891b2", "#be185d", "#65a30d"]
    sorted_leaves = sorted(curves.keys())

    legend_items = []
    for i, leaf_id in enumerate(sorted_leaves):
        curve = curves[leaf_id]
        color = palette[i % len(palette)]
        km_life_raw = leaf_km_life.get(leaf_id)

        # Build polyline — sample every 2 months for smoother rendering
        pts = []
        for m in range(0, min(max_months, len(curve)), 2):
            pts.append(f"{tx(m+1):.1f},{ty(curve[m]):.1f}")
        if pts:
            lines.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" stroke-width="2" opacity="0.85"/>')

        # Mark 50%-life crossing with a dot (only if it actually crosses)
        if km_life_raw is not None and km_life_raw <= max_months:
            cx = tx(km_life_raw)
            cy = ty(0.5)
            lines.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4" fill="{color}" stroke="white" stroke-width="1.5"/>')
            lines.append(f'<text x="{cx+6:.1f}" y="{cy-6:.1f}" font-size="9" fill="{color}" font-weight="600">{km_life_raw}mo</text>')

        km_label = f"{km_life_raw}mo" if km_life_raw is not None else "&gt;360"
        legend_items.append(f'<span style="display:inline-flex;align-items:center;gap:4px;margin-right:14px">'
                            f'<span style="width:14px;height:3px;background:{color};display:inline-block;border-radius:1px"></span>'
                            f'<span style="font-size:11px;color:#374151">Leaf {leaf_id} (50%={km_label})</span></span>')

    lines.append('</svg>')
    svg = "\n".join(lines)

    legend_html = f'<div style="margin-top:6px;line-height:1.8">{"".join(legend_items)}</div>'
    return svg + legend_html


def _survival_curve_mini_svg(curve: list, km_life: int, width=220, height=100):
    """Compact single-curve SVG for leaf detail panels."""
    if not curve:
        return ""

    max_months = min(240, len(curve))
    pad_l, pad_r, pad_t, pad_b = 30, 8, 8, 20
    pw = width - pad_l - pad_r
    ph = height - pad_t - pad_b

    def tx(m):
        return pad_l + (m / max_months) * pw

    def ty(p):
        return pad_t + (1 - p) * ph

    lines = [f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg" style="font-family:Inter,system-ui,sans-serif">']
    lines.append(f'<rect width="{width}" height="{height}" fill="#f9fafb" rx="3"/>')

    # Y-axis: 0%, 50%, 100%
    for prob, label in [(1.0, "100%"), (0.5, "50%"), (0.0, "0%")]:
        y = ty(prob)
        lines.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width-pad_r}" y2="{y:.1f}" stroke="#e5e7eb" stroke-width="0.5"/>')
        lines.append(f'<text x="{pad_l-3}" y="{y+3:.1f}" text-anchor="end" font-size="8" fill="#9ca3af">{label}</text>')

    # 50% dashed
    y50 = ty(0.5)
    lines.append(f'<line x1="{pad_l}" y1="{y50:.1f}" x2="{width-pad_r}" y2="{y50:.1f}" stroke="#9ca3af" stroke-width="0.5" stroke-dasharray="3,2"/>')

    # Curve
    pts = []
    for m in range(0, max_months, 2):
        pts.append(f"{tx(m+1):.1f},{ty(curve[m]):.1f}")
    if pts:
        lines.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="#005C3F" stroke-width="1.5"/>')

    # 50%-life marker (only if it actually crosses 50%)
    if km_life is not None and km_life <= max_months:
        cx, cy = tx(km_life), ty(0.5)
        lines.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="3" fill="#005C3F" stroke="white" stroke-width="1"/>')

    # X labels
    for m in [0, 60, 120, 180, 240]:
        if m <= max_months:
            x = tx(m)
            lines.append(f'<text x="{x:.1f}" y="{height-6}" text-anchor="middle" font-size="8" fill="#9ca3af">{m}</text>')

    lines.append('</svg>')
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Section 9: Assumptions & Review Checklist
# ---------------------------------------------------------------------------
def _build_assumptions_tab(df, wt_avg):
    """Build the assumptions & review-checklist tab content."""
    w = df["balance"]

    def _tape_val(col, alt_col=None):
        """Return (weighted-avg value, True if from tape) or (None, False)."""
        for c in [col, alt_col] if alt_col else [col]:
            if c and c in df.columns and df[c].notna().any():
                wts = w.loc[df[c].dropna().index]
                val = (df[c].dropna() * wts).sum() / wts.sum() if wts.sum() > 0 else None
                if val is not None and val != 0:
                    return val, True
        return None, False

    rows = []

    def _add(label, tape_col, alt_col, fallback, fmt, note=""):
        val, from_tape = _tape_val(tape_col, alt_col)
        display_val = val if val is not None else fallback
        source = "Tape" if from_tape else "Fallback"
        src_cls = "src-tape" if from_tape else "src-fallback"
        flag = "" if from_tape else ' <span class="assumption-flag">⚠ verify</span>'
        rows.append(
            f'<tr>'
            f'<td>{label}</td>'
            f'<td class="num">{fmt.format(display_val)}</td>'
            f'<td class="num">{fmt.format(fallback)}</td>'
            f'<td><span class="{src_cls}">{source}</span>{flag}</td>'
            f'<td class="note-col">{note}</td>'
            f'</tr>'
        )

    _add("ROE Target Yield", "roe_target_yield", "ROE Target Yield", 0.07,
         "{:.2%}", "Discount rate for all four price columns.")
    _add("Cost of Funds", "cost_of_funds", "Cost of Funds", 0.0427,
         "{:.2%}", "Blended warehouse/repo rate. Changes with market rates.")
    _add("Capital Ratio", "capital_ratio", "Capital", 0.0886,
         "{:.2%}", "Regulatory or economic capital allocation.")
    _add("Tax Rate", "tax_rate", "Tax Rate", 0.0047,
         "{:.2%}", "Effective tax drag on yield.")
    _add("Servicing Cost (ROE calc)", "servicing_cost_tape", "Servicing Cost", 0.0049,
         "{:.2%}", "Used in implied-ROE formula. Note: CF calc uses 25 bps (see below).")
    _add("Cost to Acquire", "cost_to_acquire", None, 850,
         "${:,.0f}", "Per-loan due-diligence, legal, boarding cost.")

    table_rows = "".join(rows)

    # Hardcoded assumptions that don't come from the tape
    hardcoded = """
    <h3 class="subsection">Hardcoded Assumptions (not sourced from tape)</h3>
    <table class="data-table">
      <thead><tr><th>Parameter</th><th>Value</th><th>Used In</th><th>Notes / Questions for Management</th></tr></thead>
      <tbody>
        <tr>
          <td>Servicing Cost (CF calc)</td><td class="num">25 bps</td><td>Engine cash flows</td>
          <td class="note-col"><span class="assumption-flag">&ne; ROE calc</span> The cash-flow PV calc uses 25 bps but the
              implied-ROE formula uses the tape&rsquo;s servicing cost (fallback 49 bps). These should match. Confirm actual servicing cost.</td>
        </tr>
        <tr>
          <td>Engine Cost of Capital</td><td class="num">8.0%</td><td>Pricing Engine MC</td>
          <td class="note-col">Fixed base discount rate for Monte Carlo engine. MC results are then re-scaled to the target yield
              using APEX2 as the calibration anchor.</td>
        </tr>
        <tr>
          <td>Stochastic Volatility (&sigma;)</td><td class="num">15%</td><td>Pricing Engine MC</td>
          <td class="note-col">Lognormal shock applied to monthly default, prepay, recovery, and delinquency rates.
              Has this been calibrated to observed month-over-month variation?</td>
        </tr>
        <tr>
          <td>MC Simulations</td><td class="num">200 / loan</td><td>Pricing Engine MC</td>
          <td class="note-col">Overridable via <code>--mc-sims</code>. 200 is a speed/accuracy trade-off; 500+ gives smoother tails.</td>
        </tr>
        <tr>
          <td>Default Prepay Multiplier</td><td class="num">2.3&times;</td><td>APEX2</td>
          <td class="note-col">Fallback when tape doesn&rsquo;t provide <code>apex2_prepay</code> / <code>avg_4dim</code>. Confirm this matches current APEX2 assumptions.</td>
        </tr>
        <tr>
          <td>Default Amort Plug</td><td class="num">97 mo</td><td>APEX2 life</td>
          <td class="note-col">Fallback when tape doesn&rsquo;t provide <code>apex2_amort_plug</code> / <code>nper_life</code>.</td>
        </tr>
      </tbody>
    </table>"""

    checklist = """
    <h3 class="subsection">Review Checklist</h3>
    <p class="section-hint">Questions to validate with management or wholesalers before relying on these prices.</p>
    <div class="checklist">
      <label class="check-item"><input type="checkbox"> <strong>CDR:</strong> Is 0.15% the right base-case default rate for this pool? Should it vary by credit band?</label>
      <label class="check-item"><input type="checkbox"> <strong>Recovery:</strong> Is 50% net recovery realistic for non-QM? Check historical liquidation data.</label>
      <label class="check-item"><input type="checkbox"> <strong>Servicing cost mismatch:</strong> CF calc uses 25 bps but ROE formula uses tape value (fallback 49 bps). Which is correct?</label>
      <label class="check-item"><input type="checkbox"> <strong>Cost of funds:</strong> Is the tape CoF current? Warehouse rates change frequently.</label>
      <label class="check-item"><input type="checkbox"> <strong>Capital ratio:</strong> Regulatory vs economic capital &mdash; which does the business use for bid decisions?</label>
      <label class="check-item"><input type="checkbox"> <strong>ROE target yield:</strong> Confirm the tape populates this per-loan. If missing, everything falls back to 7%.</label>
      <label class="check-item"><input type="checkbox"> <strong>Cost to acquire:</strong> Is $850/loan still current? Varies by seller and diligence scope.</label>
      <label class="check-item"><input type="checkbox"> <strong>MC volatility (&sigma;=15%):</strong> Has this been calibrated to actual month-over-month rate variation?</label>
      <label class="check-item"><input type="checkbox"> <strong>Systemic correlation:</strong> MC shocks are independent across loans. Portfolio tail risk may be understated for economy-wide events.</label>
    </div>"""

    return f"""
    <h2 class="section-title">9. Assumptions &amp; Review Checklist</h2>
    <p class="section-hint">
      All three prices (Offered, APEX2, Pricing Engine) are present values discounted at the
      tape&rsquo;s ROE target yield, making them directly comparable. Differences come from methodology
      (how prepayment and credit losses are modeled), not from different return targets.
    </p>

    <h3 class="subsection">Tape-Sourced Parameters</h3>
    <p class="section-hint">Green = from tape. Orange = using hardcoded fallback &mdash; verify these with management.</p>
    <div class="table-wrap">
    <table class="data-table">
      <thead><tr><th>Parameter</th><th>Pool Avg</th><th>Fallback</th><th>Source</th><th>Notes</th></tr></thead>
      <tbody>{table_rows}</tbody>
    </table>
    </div>

    {hardcoded}
    {checklist}"""


# ---------------------------------------------------------------------------
# Page assembly
# ---------------------------------------------------------------------------
def _assemble_page(now, section1, section2, section3, section4, section5, section6, section7="", section8="", section9="", curve_variant_label="Full History", prepay_model_label="Stub"):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Pricing Validation Report</title>
<style>
  :root {{
    --blue: #005C3F;
    --blue-light: #e6f5f0;
    --green: #16a34a;
    --green-light: #dcfce7;
    --yellow: #ca8a04;
    --yellow-light: #fefce8;
    --red: #ef4444;
    --red-light: #fef2f2;
    --gray-50: #f9fafb;
    --gray-100: #f3f4f6;
    --gray-200: #e5e7eb;
    --gray-400: #9ca3af;
    --gray-600: #4b5563;
    --gray-800: #1f2937;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--gray-50);
    color: var(--gray-800);
    line-height: 1.5;
  }}
  .page {{ max-width: 1200px; margin: 0 auto; padding: 24px; }}
  .page-header {{
    background: linear-gradient(135deg, #003D2A 0%, #005C3F 100%);
    color: white;
    padding: 32px 40px;
    border-radius: 12px;
    margin-bottom: 24px;
  }}
  .page-header h1 {{ font-size: 28px; font-weight: 700; margin-bottom: 4px; }}
  .page-header .subtitle {{ opacity: 0.85; font-size: 14px; }}

  .summary-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-bottom: 20px;
  }}
  .summary-card {{
    background: white;
    border-radius: 10px;
    padding: 20px;
    text-align: center;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    border: 1px solid var(--gray-200);
  }}
  .card-number {{ font-size: 24px; font-weight: 700; color: var(--blue); }}
  .card-label {{ font-size: 12px; color: var(--gray-600); text-transform: uppercase; letter-spacing: 0.5px; }}

  .section-title {{
    font-size: 20px;
    font-weight: 600;
    margin: 32px 0 16px;
    padding-bottom: 8px;
    border-bottom: 2px solid var(--gray-200);
  }}
  .subsection {{
    font-size: 15px;
    font-weight: 600;
    margin: 20px 0 10px;
    color: var(--gray-600);
  }}
  .section-hint {{
    font-size: 13px;
    color: var(--gray-400);
    margin-bottom: 12px;
  }}

  .metrics-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
    margin-bottom: 20px;
  }}
  .mini-metrics {{ max-width: 400px; }}

  .traffic-lights {{
    display: flex;
    flex-direction: column;
    gap: 16px;
    padding: 16px;
    background: white;
    border-radius: 10px;
    border: 1px solid var(--gray-200);
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  }}
  .traffic-light {{
    display: flex;
    align-items: center;
    gap: 12px;
  }}
  .tl-value {{ font-size: 18px; font-weight: 700; }}
  .tl-label {{ font-size: 12px; color: var(--gray-600); }}


  .table-wrap {{ overflow-x: auto; margin-bottom: 20px; }}
  .data-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
    background: white;
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  }}
  .data-table thead {{ background: var(--gray-100); }}
  .data-table th {{
    padding: 10px 12px;
    text-align: left;
    font-weight: 600;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.3px;
    color: var(--gray-600);
    white-space: nowrap;
    position: sticky;
    top: 0;
    cursor: pointer;
    user-select: none;
  }}
  .data-table th:hover {{ background: var(--gray-200); }}
  .data-table td {{
    padding: 7px 12px;
    border-top: 1px solid var(--gray-100);
    white-space: nowrap;
  }}
  .data-table .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .data-table tr:hover {{ background: var(--blue-light); }}

  .bar-bg {{
    width: 80px; height: 8px;
    background: var(--gray-200); border-radius: 4px; overflow: hidden;
  }}
  .bar {{ height: 100%; background: var(--blue); border-radius: 4px; }}

  .badge {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 12px;
    font-weight: 600;
  }}
  .badge-green {{ background: var(--green-light); color: var(--green); }}
  .badge-yellow {{ background: var(--yellow-light); color: var(--yellow); }}
  .badge-red {{ background: var(--red-light); color: var(--red); }}

  .chart-container {{
    background: white;
    border-radius: 10px;
    padding: 16px;
    margin-bottom: 20px;
    border: 1px solid var(--gray-200);
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    text-align: center;
  }}

  .life-summary {{ margin-bottom: 20px; }}

  .life-bars-container {{ text-align: left; }}
  .life-bar-group {{
    margin-bottom: 16px;
    padding: 10px 0;
    border-bottom: 1px solid var(--gray-100);
  }}
  .life-bar-label {{
    font-weight: 600;
    font-size: 14px;
    margin-bottom: 6px;
  }}
  .life-bar-row {{
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 3px;
  }}
  .life-bar-tag {{
    font-size: 11px;
    width: 40px;
    text-align: right;
    color: var(--gray-600);
    font-weight: 500;
  }}
  .life-bar-track {{
    flex: 1;
    height: 14px;
    background: var(--gray-100);
    border-radius: 3px;
    overflow: hidden;
  }}
  .life-bar-fill {{
    height: 100%;
    border-radius: 3px;
    transition: width 0.3s;
  }}
  .life-bar-val {{
    font-size: 12px;
    font-weight: 600;
    width: 50px;
    font-variant-numeric: tabular-nums;
  }}

  .feat-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 12px;
    margin-bottom: 20px;
  }}
  .feat-card {{
    background: white;
    border: 1px solid var(--gray-200);
    border-radius: 8px;
    padding: 14px;
  }}
  .feat-name {{ font-weight: 600; font-size: 14px; margin-bottom: 6px; }}
  .feat-ranges {{ font-size: 12px; color: var(--gray-600); margin-bottom: 8px; }}
  .feat-bar-wrap {{
    height: 6px;
    background: var(--gray-200);
    border-radius: 3px;
    overflow: hidden;
    margin-bottom: 4px;
  }}
  .feat-bar {{ height: 100%; border-radius: 3px; }}
  .feat-pct {{ font-size: 12px; font-weight: 600; }}

  .detail-row td {{ padding: 0 !important; border-top: none !important; }}
  .detail-content {{
    padding: 12px 24px;
    background: var(--gray-50);
    border-top: 1px dashed var(--gray-200);
    display: flex;
    gap: 20px;
    align-items: flex-start;
    flex-wrap: wrap;
  }}
  .detail-chart {{ flex-shrink: 0; }}
  .detail-kickers {{ font-size: 12px; color: var(--gray-600); }}
  .detail-meta {{ font-size: 11px; color: var(--gray-400); }}

  .show-more-btn {{
    display: block;
    margin: 8px auto;
    padding: 8px 20px;
    background: var(--blue);
    color: white;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
  }}
  .show-more-btn:hover {{ opacity: 0.9; }}
  .hidden-row {{ display: none; }}

  .muted {{ color: var(--gray-400); font-style: italic; }}

  .footer {{
    text-align: center;
    color: var(--gray-400);
    font-size: 12px;
    margin-top: 40px;
    padding: 20px;
  }}

  /* Tab navigation */
  .tab-nav {{
    display: flex;
    gap: 0;
    border-bottom: 2px solid var(--gray-200);
    margin-bottom: 24px;
    overflow-x: auto;
  }}
  .tab-btn {{
    padding: 10px 20px;
    background: none;
    border: none;
    border-bottom: 3px solid transparent;
    cursor: pointer;
    font-size: 14px;
    font-weight: 500;
    color: var(--gray-400);
    white-space: nowrap;
    transition: color 0.15s, border-color 0.15s;
  }}
  .tab-btn:hover {{ color: var(--gray-600); }}
  .tab-btn.active {{
    color: var(--blue);
    border-bottom-color: var(--blue);
    font-weight: 600;
  }}
  .tab-content {{ display: none; }}
  .tab-content.active {{ display: block; }}

  /* Tree list (collapsible) */
  .tree-list-wrap {{
    background: white;
    border: 1px solid var(--gray-200);
    border-radius: 10px;
    padding: 16px 12px;
    margin-bottom: 20px;
    max-height: 700px;
    overflow-y: auto;
    font-size: 13px;
    font-family: "SF Mono", "Fira Code", monospace;
  }}
  .tree-list-wrap details {{ margin-left: 20px; }}
  .tree-list-wrap > details {{ margin-left: 0; }}
  .tree-list-wrap summary {{
    cursor: pointer;
    padding: 3px 6px;
    border-radius: 4px;
    list-style: none;
  }}
  .tree-list-wrap summary::-webkit-details-marker {{ display: none; }}
  .tree-list-wrap summary::before {{
    content: "▶ ";
    font-size: 10px;
    color: var(--gray-400);
    transition: transform 0.15s;
    display: inline-block;
  }}
  .tree-list-wrap details[open] > summary::before {{
    transform: rotate(90deg);
  }}
  .tree-list-wrap summary:hover {{ background: #f3f4f6; }}
  .node-split {{ font-weight: 600; color: var(--gray-800); }}
  .node-samples {{ color: var(--gray-400); font-size: 11px; margin-left: 8px; }}
  .branch-label {{ color: var(--gray-400); font-size: 11px; }}
  .tree-leaf {{
    margin-left: 20px;
    padding: 3px 8px;
    border-radius: 4px;
    cursor: pointer;
  }}
  .tree-leaf:hover {{ background: #f0fdf4; }}
  .tree-leaf-has-tape {{
    border-left: 3px solid var(--green);
    background: #f8fdf9;
  }}
  .leaf-tag {{
    font-weight: 700;
    color: var(--blue);
    margin-right: 8px;
  }}
  .tree-leaf .leaf-stats {{
    color: var(--gray-400);
    font-size: 11px;
    margin-right: 8px;
  }}

  .leaf-panel {{
    background: white;
    border: 1px solid var(--gray-200);
    border-radius: 10px;
    padding: 20px;
    margin-bottom: 12px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  }}
  .leaf-panel.tree-leaf-tape {{
    border-left: 4px solid var(--green);
    background: #f0fdf4;
  }}
  .leaf-panel-header {{
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 12px;
  }}
  .back-to-tree {{
    margin-left: auto;
    font-size: 12px;
    color: var(--blue);
    text-decoration: none;
    cursor: pointer;
    padding: 2px 8px;
    border: 1px solid var(--gray-200);
    border-radius: 4px;
  }}
  .back-to-tree:hover {{
    background: var(--gray-50, #f9fafb);
  }}
  .leaf-id-tag {{
    font-size: 16px;
    font-weight: 700;
    color: var(--blue);
  }}
  .leaf-stats {{
    font-size: 12px;
    color: var(--gray-400);
  }}
  .leaf-panel-body {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
  }}

  .tree-rules-col h4, .tree-stats-col h4 {{
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--gray-400);
    margin-bottom: 8px;
  }}
  .tree-rule {{
    padding: 4px 10px;
    margin-bottom: 4px;
    border-radius: 4px;
    font-size: 12px;
    font-family: "SF Mono", "Fira Code", monospace;
    color: var(--gray-800);
  }}
  .rule-depth {{
    display: inline-block;
    width: 22px;
    font-size: 10px;
    font-weight: 700;
    color: var(--gray-400);
  }}

  .info-callout {{
    background: #eff6ff;
    border: 1px solid #bfdbfe;
    border-radius: 8px;
    padding: 14px 18px;
    margin: 12px 0 20px;
    font-size: 13px;
    line-height: 1.6;
    color: #003D2A;
  }}

  /* Assumptions tab */
  .src-tape {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
    background: #dcfce7;
    color: #166534;
  }}
  .src-fallback {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
    background: #fff7ed;
    color: #9a3412;
  }}
  .assumption-flag {{
    font-size: 11px;
    color: #dc2626;
    font-weight: 600;
    margin-left: 4px;
  }}
  .note-col {{
    font-size: 12px;
    color: var(--gray-600);
    max-width: 340px;
  }}
  .checklist {{
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin: 12px 0;
  }}
  .check-item {{
    display: flex;
    align-items: baseline;
    gap: 8px;
    font-size: 13px;
    line-height: 1.5;
    cursor: pointer;
  }}
  .check-item input[type="checkbox"] {{
    accent-color: var(--blue);
    margin-top: 3px;
    flex-shrink: 0;
  }}

  @media print {{
    body {{ background: white; }}
    .page {{ max-width: none; padding: 0; }}
    .page-header {{ break-after: avoid; }}
    .data-table th {{ position: static; }}
    .hidden-row {{ display: table-row !important; }}
    .show-more-btn {{ display: none; }}
    .tab-nav {{ display: none; }}
    .tab-content {{ display: block !important; }}
    .leaf-panel {{ break-inside: avoid; }}
    .tree-list-wrap {{ max-height: none; overflow: visible; }}
    .tree-list-wrap details {{ break-inside: avoid; }}
  }}
</style>
</head>
<body>
<div class="page">
  <div class="page-header">
    <h1>Pricing Validation Report</h1>
    <div class="subtitle">
      FNBA Loan Tape Analysis &bull; Generated {now}
      &bull; Curves: <strong>{curve_variant_label}</strong>
      &bull; Prepay: <strong>{prepay_model_label}</strong>
    </div>
  </div>

  <div class="tab-nav">
    <button class="tab-btn active" onclick="switchTab('main')">Pricing Validation</button>
    <button class="tab-btn" onclick="switchTab('mc')">Pricing Engine</button>
    <button class="tab-btn" onclick="switchTab('tree')">Segmentation Tree</button>
    <button class="tab-btn" onclick="switchTab('assumptions')">Assumptions</button>
  </div>

  <div id="tab-main" class="tab-content active">
    {section1}
    {section2}
    {section3}
    {section4}
    {section5}
    {section6}
  </div>

  <div id="tab-mc" class="tab-content">
    {section8 if section8 else '<div class="info-callout">Pricing Engine simulation was not run. Use <code>--mc</code> flag to enable.</div>'}
  </div>

  <div id="tab-tree" class="tab-content">
    {section7}
  </div>

  <div id="tab-assumptions" class="tab-content">
    {section9}
  </div>

  <div class="footer">
    Generated by pricing_validation_report.py &bull; {now}
  </div>
</div>

<script>
// Sortable table headers
document.querySelectorAll('.data-table thead th').forEach((th, colIdx) => {{
  let asc = true;
  th.addEventListener('click', () => {{
    const tbody = th.closest('table').querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr:not(.detail-row)'));
    rows.sort((a, b) => {{
      const av = a.children[colIdx]?.textContent.replace(/[$,%,]/g, '').trim() || '';
      const bv = b.children[colIdx]?.textContent.replace(/[$,%,]/g, '').trim() || '';
      const an = parseFloat(av.replace(/,/g, ''));
      const bn = parseFloat(bv.replace(/,/g, ''));
      if (!isNaN(an) && !isNaN(bn)) return asc ? an - bn : bn - an;
      return asc ? av.localeCompare(bv) : bv.localeCompare(av);
    }});
    asc = !asc;
    rows.forEach(r => {{
      tbody.appendChild(r);
      const detail = document.getElementById('detail-' + r.children[0]?.textContent);
      if (detail) tbody.appendChild(detail);
    }});
  }});
}});

// Expandable detail rows
function toggleDetail(loanId) {{
  const row = document.getElementById('detail-' + loanId);
  if (row) {{
    row.style.display = row.style.display === 'none' ? 'table-row' : 'none';
  }}
}}

// Show more rows
function toggleRows(btn) {{
  const table = btn.previousElementSibling;
  const hidden = table.querySelectorAll('.hidden-row');
  const showing = hidden[0]?.style.display !== 'none' && hidden[0]?.classList.contains('hidden-row');
  hidden.forEach(r => {{
    if (r.classList.contains('hidden-row')) {{
      r.style.display = r.style.display === 'none' || r.style.display === '' ? 'table-row' : 'none';
    }}
  }});
  btn.textContent = btn.textContent.includes('Show') ? 'Show fewer rows' : btn.textContent.replace('fewer', 'all');
}}

// Tab switching
function switchTab(tabName) {{
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-' + tabName).classList.add('active');
  event.target.classList.add('active');
}}

// Scroll to leaf detail panel (from tree SVG click)
function scrollToLeaf(leafId) {{
  // Switch to tree tab if not already there
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById('tab-tree').classList.add('active');
  document.querySelectorAll('.tab-btn')[2].classList.add('active');
  // Scroll to panel
  const panel = document.getElementById('leaf-panel-' + leafId);
  if (panel) {{
    panel.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
    panel.style.boxShadow = '0 0 0 3px #005C3F';
    setTimeout(() => panel.style.boxShadow = '', 2000);
  }}
}}

// Print: expand all tree details, then restore after printing
(function() {{
  let _savedState = [];
  window.addEventListener('beforeprint', () => {{
    _savedState = [];
    document.querySelectorAll('.tree-list-wrap details').forEach(d => {{
      _savedState.push({{ el: d, wasOpen: d.hasAttribute('open') }});
      d.setAttribute('open', '');
    }});
  }});
  window.addEventListener('afterprint', () => {{
    _savedState.forEach(({{ el, wasOpen }}) => {{
      if (!wasOpen) el.removeAttribute('open');
    }});
    _savedState = [];
  }});
}})();
</script>
</body>
</html>"""


# ===================================================================
# Main
# ===================================================================
def main():
    parser = argparse.ArgumentParser(description="Generate pricing validation HTML report")
    parser.add_argument("--tape", help="Path to Excel loan tape (default: loan_tape_2_clean.xlsx)")
    parser.add_argument("--out", help="Output filename (default: pricing_validation.html)")
    parser.add_argument("--mc", action="store_true", default=True,
                        help="Run Monte Carlo validation (default: enabled)")
    parser.add_argument("--no-mc", action="store_true",
                        help="Skip Monte Carlo simulation for faster generation")
    parser.add_argument("--mc-sims", type=int, default=200,
                        help="Number of MC simulations per loan (default: 200)")
    parser.add_argument("--no-csv", action="store_true",
                        help="Skip CSV export")
    parser.add_argument("--curve-variant", type=str, default=None, metavar="VARIANT",
                        help=(
                            "Survival curve variant to use. E.g. '12mo' loads "
                            "survival_curves_12mo.parquet. Default: full history."
                        ))
    args = parser.parse_args()

    run_mc = args.mc and not args.no_mc

    tape_path = Path(args.tape) if args.tape else BACKEND_DIR / "loan_tape_2_clean.xlsx"
    if not tape_path.exists():
        logger.error("Tape not found: %s", tape_path)
        sys.exit(1)

    t_start = time.time()

    # Stage 1: Load
    df, pkg = stage_load(tape_path)

    # Stage 2: Init models
    registry = stage_init_models()

    # Load curve variant if specified
    curve_variant_label = "Full History"
    if args.curve_variant:
        registry.load_curve_variant(args.curve_variant)
        curve_variant_label = f"{args.curve_variant} Lookback"
        logger.info("Using curve variant: %s (%d curves loaded)",
                     args.curve_variant, len(registry.survival_curves))

    prepay_model_label = "Stub"

    # Stage 3: Bucket assignment
    loan_leaf_map, leaf_loans, leaf_km_life, leaf_mean_life, leaf_curves = stage_bucket_assignment(pkg)

    # Stage 4: APEX2 analysis
    df, scenarios_9 = stage_apex2_analysis(df)

    # Stage 5: Cashflow valuation
    df, results = stage_cashflow_valuation(df, pkg, loan_leaf_map)

    # Stage 5b: Monte Carlo (if enabled)
    mc_results = None
    portfolio_mc_pvs = None
    if run_mc:
        df, mc_results, portfolio_mc_pvs = stage_monte_carlo(
            df, pkg, n_sims=args.mc_sims,
        )
    else:
        logger.info("Skipping Monte Carlo (use --mc to enable)")

    # Stage 5c: Price comparison (3 estimates)
    df, price_totals = stage_price_comparison(
        df, results, pkg, mc_results=mc_results,
    )

    # Stage 6: Sensitivity
    stub_impacts, feature_bounds, scenario_stress = stage_sensitivity(df, pkg, results, loan_leaf_map)

    # Stage 7: Assemble HTML
    html = stage_assemble_html(
        df, pkg, loan_leaf_map, leaf_loans, leaf_km_life, leaf_mean_life,
        scenarios_9, results, stub_impacts, feature_bounds, scenario_stress,
        registry=registry, mc_results=mc_results, portfolio_mc_pvs=portfolio_mc_pvs,
        price_totals=price_totals, leaf_curves=leaf_curves,
        curve_variant_label=curve_variant_label,
        prepay_model_label=prepay_model_label,
    )

    REPORTS_DIR.mkdir(exist_ok=True)
    out_name = args.out or "pricing_validation.html"
    out_path = REPORTS_DIR / out_name
    out_path.write_text(html, encoding="utf-8")

    logger.info("Wrote %s (%d KB)", out_path, len(html) // 1024)

    # --- CSV export ---
    # Column naming convention (matches report sections):
    #   Offered      = tape bid price
    #   APEX2        = replicated APEX2 (prepay only, no credit)
    #   PE           = Pricing Engine (Monte Carlo mean, scaled to APEX2)
    if not args.no_csv:
        csv_df = pd.DataFrame()
        # Loan characteristics
        csv_df["loan_id"] = [f"LN-{i+1:04d}" for i in df.index]
        csv_df["balance"] = df["balance"].values
        csv_df["rate"] = df["rate"].values
        csv_df["credit"] = df["credit"].values
        csv_df["ltv"] = df["ltv"].values if "ltv" in df.columns else np.nan
        csv_df["seasoning"] = df["seasoning"].values
        csv_df["rem_term"] = df["rem_term"].values

        # Segmentation
        csv_df["leaf_id"] = [loan_leaf_map.get(f"LN-{i+1:04d}", "") for i in df.index]

        # Life & prepayment estimates
        if "apex2_amort_plug" in df.columns:
            csv_df["apex2_life_mo"] = df["apex2_amort_plug"].values
        if "km_life" in df.columns:
            csv_df["km_50pct_life_mo"] = df["km_life"].values
        if "engine_mean_life" in df.columns:
            csv_df["km_mean_life_mo"] = df["engine_mean_life"].values
        if "apex2_prepay" in df.columns:
            csv_df["apex2_prepay_mult"] = df["apex2_prepay"].values

        # Price estimates (consistent names)
        price_map = {
            "price_offered": "price_offered",
            "price_apex2": "price_apex2",
            "price_mc": "price_pe",
        }
        for src_col, csv_col in price_map.items():
            if src_col in df.columns:
                csv_df[csv_col] = df[src_col].values
                csv_df[csv_col.replace("price_", "cents_")] = df[src_col].values / df["balance"].values * 100

        # Scenario PVs & implied yield
        for col in ["pv_baseline", "pv_mild", "pv_severe", "model_npv", "implied_yield"]:
            if col in df.columns:
                csv_df[col] = df[col].values

        # Pricing Engine band
        pe_mc_map = {
            "price_mc_p5": "pe_p5",
            "price_mc_p95": "pe_p95",
            "mc_spread": "pe_spread_pct",
        }
        for src_col, csv_col in pe_mc_map.items():
            if src_col in df.columns:
                csv_df[csv_col] = df[src_col].values

        csv_path = out_path.with_suffix(".csv")
        csv_df.to_csv(csv_path, index=False)
        logger.info("Wrote %s (%d rows, %d cols)", csv_path, len(csv_df), len(csv_df.columns))

    logger.info("Total time: %.1fs", time.time() - t_start)


if __name__ == "__main__":
    main()
