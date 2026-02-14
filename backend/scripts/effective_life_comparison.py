#!/usr/bin/env python3
"""Effective Life Comparison — APEX2 vs KM Survival.

Compares two independent effective life estimates for each loan:
  - APEX2: FNBA's production 4-dimensional prepayment model
  - KM survival curves: empirical from the segmentation tree's 4.4M training loans

Outputs:
  - reports/effective_life_comparison.html  (management-ready self-contained HTML)
  - reports/effective_life_comparison.csv   (per-loan detail for Excel)

Usage:
    cd backend && python scripts/effective_life_comparison.py
    cd backend && python scripts/effective_life_comparison.py --tape other.xlsx
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
    get_rate_delta_band,
)
from app.services.tape_parser import parse_loan_tape
from app.ml.model_loader import ModelRegistry
from app.ml.bucket_assigner import assign_bucket
from app.ml.curve_provider import get_survival_curve


# ---------------------------------------------------------------------------
# KM helpers
# ---------------------------------------------------------------------------
def km_50pct_life(curve: list[float]) -> int:
    """First month where survival <= 0.5."""
    idx = next((i for i, s in enumerate(curve) if s <= 0.5), len(curve))
    return idx + 1


def km_mean_life(curve: list[float]) -> float:
    """Expected life = area under survival curve."""
    return sum(curve)


def km_conditional_remaining_life(curve: list[float], age_months: int) -> int:
    """Months until 50% of survivors-to-age pay off."""
    if age_months <= 0:
        idx = next((i for i, s in enumerate(curve) if s <= 0.5), len(curve))
        return idx + 1
    age_idx = age_months - 1  # curve[0] = S(month 1)
    if age_idx >= len(curve):
        return 0
    s_age = curve[age_idx]
    if s_age <= 0:
        return 0
    for t in range(age_idx + 1, len(curve)):
        if curve[t] / s_age <= 0.5:
            return t - age_idx  # remaining months
    return len(curve) - age_months


# ===================================================================
# STAGE 1: Load Data
# ===================================================================
def stage_load(tape_path: Path):
    logger.info("Stage 1: Loading data from %s", tape_path.name)
    t0 = time.time()

    df = load_tape(tape_path)
    logger.info("  Loaded %d loans into DataFrame", len(df))

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
# STAGE 3: Per-Loan Life Computation
# ===================================================================
def stage_compute_lives(df, pkg):
    logger.info("Stage 3: Computing per-loan effective lives")
    t0 = time.time()

    has_tape_mult = "apex2_prepay" in df.columns and df["apex2_prepay"].notna().any()

    # Compute APEX2 4-dim multipliers
    mult_rows = []
    for _, row in df.iterrows():
        mult_rows.append(compute_apex2_multiplier(
            row["credit"], row["rate"],
            row.get("ltv", 60), row["balance"],
        ))
    for key in mult_rows[0]:
        df[key] = [m[key] for m in mult_rows]

    # Build loan lookup for assign_bucket
    loan_lookup = {}
    for i, loan in enumerate(pkg.loans):
        loan_lookup[i] = loan

    # Per-loan computation
    apex2_proj_tape = []
    apex2_proj_4dim = []
    apex2_proj_flat = []
    apex2_nper_vals = []
    leaf_ids = []
    km_50_vals = []
    km_mean_vals = []
    km_remaining_vals = []
    divergence_months_list = []
    divergence_flag_list = []

    for idx, row in df.iterrows():
        bal = row["balance"]
        pandi = row["pandi"]
        rate = row["rate"]
        seasoning = row["seasoning"]
        rem = int(row["rem_term"])

        # APEX2 lives — tape multiplier
        tape_mult = row.get("apex2_prepay", row["avg_4dim"]) if has_tape_mult else row["avg_4dim"]
        life_tape = project_effective_life(bal, pandi, rate, tape_mult, seasoning, rem, use_seasoning=True)
        apex2_proj_tape.append(life_tape)

        # APEX2 lives — 4-dim computed multiplier
        mult_4d = row["avg_4dim"]
        life_4dim = project_effective_life(bal, pandi, rate, mult_4d, seasoning, rem, use_seasoning=True)
        apex2_proj_4dim.append(life_4dim)

        # APEX2 lives — flat (no seasoning)
        life_flat = project_effective_life(bal, pandi, rate, tape_mult, seasoning, rem, use_seasoning=False)
        apex2_proj_flat.append(life_flat)

        # APEX2 NPER
        nper = apex2_amortize(bal, pandi * tape_mult, rate, 12)
        apex2_nper_vals.append(nper)

        # KM lives via leaf assignment
        if idx < len(pkg.loans):
            ld = pkg.loans[idx].model_dump()
            leaf_id = assign_bucket(ld)
            loan_age = int(seasoning)
        else:
            leaf_id = 1
            loan_age = 0

        leaf_ids.append(leaf_id)
        curve = get_survival_curve(leaf_id, 360)

        km_50 = km_50pct_life(curve)
        km_mean = km_mean_life(curve)
        km_rem = km_conditional_remaining_life(curve, loan_age)

        km_50_vals.append(km_50)
        km_mean_vals.append(km_mean)
        km_remaining_vals.append(km_rem)

        # Divergence
        div_mo = life_tape - km_50
        divergence_months_list.append(div_mo)
        divergence_flag_list.append(abs(div_mo) > 24)

    df["apex2_proj_tape"] = apex2_proj_tape
    df["apex2_proj_4dim"] = apex2_proj_4dim
    df["apex2_proj_flat"] = apex2_proj_flat
    df["apex2_nper"] = apex2_nper_vals
    df["leaf_id"] = leaf_ids
    df["km_50pct_life"] = km_50_vals
    df["km_mean_life"] = km_mean_vals
    df["km_remaining_life"] = km_remaining_vals
    df["divergence_months"] = divergence_months_list
    df["divergence_flag"] = divergence_flag_list
    df["credit_band"] = df["credit"].apply(get_credit_band)
    df["rate_delta_band"] = df["rate"].apply(get_rate_delta_band)

    n_flagged = sum(divergence_flag_list)
    logger.info("  %d/%d loans have >24mo divergence", n_flagged, len(df))
    logger.info("  Stage 3 done (%.1fs)", time.time() - t0)
    return df


# ===================================================================
# STAGE 4: Aggregation
# ===================================================================
def stage_aggregate(df):
    logger.info("Stage 4: Aggregating by leaf and credit band")
    t0 = time.time()

    w = df["balance"]
    total_upb = w.sum()

    life_cols = [
        "apex2_proj_tape", "apex2_proj_4dim", "apex2_proj_flat", "apex2_nper",
        "km_50pct_life", "km_mean_life", "km_remaining_life",
    ]

    def weighted_agg(group):
        gw = group["balance"]
        gupb = gw.sum()
        result = {"count": len(group), "upb": gupb}
        for col in life_cols:
            vals = group[col].dropna()
            wts = gw.loc[vals.index]
            result[col] = (vals * wts).sum() / wts.sum() if wts.sum() > 0 else 0
        result["divergence_months"] = result["apex2_proj_tape"] - result["km_50pct_life"]
        result["pct_flagged"] = group["divergence_flag"].mean() * 100
        return pd.Series(result)

    by_leaf = df.groupby("leaf_id").apply(weighted_agg, include_groups=False).reset_index()
    by_credit = df.groupby("credit_band").apply(weighted_agg, include_groups=False).reset_index()

    # Preserve credit band ordering
    band_order = ["<576", "576-600", "601-625", "626-650", "651-675",
                  "676-700", "701-725", "726-750", ">=751"]
    by_credit["credit_band"] = pd.Categorical(by_credit["credit_band"], categories=band_order, ordered=True)
    by_credit = by_credit.sort_values("credit_band")

    logger.info("  %d leaf groups, %d credit band groups", len(by_leaf), len(by_credit))
    logger.info("  Stage 4 done (%.1fs)", time.time() - t0)
    return by_leaf, by_credit


# ===================================================================
# STAGE 5: Seasoning Sensitivity
# ===================================================================
def stage_seasoning_sensitivity(df):
    logger.info("Stage 5: Seasoning sensitivity analysis")
    t0 = time.time()

    ages = [0, 6, 12, 18, 24, 30, 36, 42, 48, 54, 60]
    w = df["balance"]
    total_upb = w.sum()

    has_tape_mult = "apex2_prepay" in df.columns and df["apex2_prepay"].notna().any()

    results = []
    for age in ages:
        # APEX2: recompute project_effective_life with overridden age
        apex2_lives = []
        km_rem_lives = []
        for idx, row in df.iterrows():
            mult = row.get("apex2_prepay", row["avg_4dim"]) if has_tape_mult else row["avg_4dim"]
            life = project_effective_life(
                row["balance"], row["pandi"], row["rate"],
                mult, age, int(row["rem_term"]), use_seasoning=True,
            )
            apex2_lives.append(life)

            # KM conditional remaining life at this age
            curve = get_survival_curve(int(row["leaf_id"]), 360)
            km_rem = km_conditional_remaining_life(curve, age)
            km_rem_lives.append(km_rem)

        wt_apex2 = (pd.Series(apex2_lives) * w).sum() / total_upb
        wt_km_rem = (pd.Series(km_rem_lives) * w).sum() / total_upb
        gap = wt_apex2 - wt_km_rem

        results.append({
            "age": age,
            "apex2_life": wt_apex2,
            "km_remaining_life": wt_km_rem,
            "gap_months": gap,
        })

    seasoning_df = pd.DataFrame(results)
    logger.info("  Stage 5 done (%.1fs)", time.time() - t0)
    return seasoning_df


# ===================================================================
# STAGE 6: Divergence Investigation
# ===================================================================
def stage_divergence_investigation(df):
    logger.info("Stage 6: Divergence investigation")
    t0 = time.time()

    flagged = df[df["divergence_flag"]].copy()
    if len(flagged) == 0:
        logger.info("  No >24mo divergences found")
        logger.info("  Stage 6 done (%.1fs)", time.time() - t0)
        return []

    # Group flagged loans by leaf
    investigations = []
    for leaf_id, group in flagged.groupby("leaf_id"):
        gw = group["balance"]
        gupb = gw.sum()
        avg_div = (group["divergence_months"] * gw).sum() / gupb if gupb > 0 else 0

        # Rate delta distribution
        rd_dist = group.groupby("rate_delta_band")["balance"].sum()
        rd_dist = (rd_dist / rd_dist.sum() * 100).to_dict()

        # APEX2 dimension breakdown
        dims = {}
        for dim_col in ["dim_credit", "dim_rate_delta", "dim_ltv", "dim_loan_size"]:
            if dim_col in group.columns:
                vals = group[dim_col]
                dims[dim_col] = (vals * gw).sum() / gupb if gupb > 0 else 0

        # Population characteristics
        pop = {
            "avg_credit": (group["credit"] * gw).sum() / gupb if gupb > 0 else 0,
            "avg_rate": (group["rate"] * gw).sum() / gupb if gupb > 0 else 0,
            "avg_ltv": (group["ltv"] * gw).sum() / gupb if "ltv" in group.columns and gupb > 0 else 0,
            "avg_seasoning": (group["seasoning"] * gw).sum() / gupb if gupb > 0 else 0,
        }

        investigations.append({
            "leaf_id": leaf_id,
            "count": len(group),
            "upb": gupb,
            "avg_divergence": avg_div,
            "rate_delta_dist": rd_dist,
            "apex2_dims": dims,
            "population": pop,
        })

    logger.info("  Investigated %d divergent segments", len(investigations))
    logger.info("  Stage 6 done (%.1fs)", time.time() - t0)
    return investigations


# ===================================================================
# CSV Export
# ===================================================================
def export_csv(df, csv_path: Path):
    logger.info("Exporting CSV to %s", csv_path)
    export_cols = [
        "balance", "rate", "credit", "ltv", "seasoning", "rem_term",
        "credit_band", "rate_delta_band", "leaf_id",
        "apex2_proj_tape", "apex2_proj_4dim", "apex2_proj_flat", "apex2_nper",
        "km_50pct_life", "km_mean_life", "km_remaining_life",
        "divergence_months", "divergence_flag",
    ]
    if "apex2_prepay" in df.columns:
        export_cols.insert(7, "apex2_prepay")
    if "apex2_amort_plug" in df.columns:
        export_cols.insert(8, "apex2_amort_plug")
    if "avg_4dim" in df.columns:
        export_cols.insert(9, "avg_4dim")

    cols = [c for c in export_cols if c in df.columns]
    df[cols].to_csv(csv_path, index=False)
    logger.info("  Wrote %d rows × %d columns", len(df), len(cols))


# ===================================================================
# HTML Report Generation
# ===================================================================
def build_html(df, by_leaf, by_credit, seasoning_df, investigations, registry=None):
    now = datetime.now().strftime("%B %d, %Y %I:%M %p")
    w = df["balance"]
    total_upb = w.sum()

    def wt_avg(series):
        valid = series.dropna()
        wts = w.loc[valid.index]
        return (valid * wts).sum() / wts.sum() if wts.sum() > 0 else 0

    # Load tree metadata for KM provenance
    km_meta = _load_km_metadata(registry)

    section1 = _build_executive_summary(df, wt_avg, total_upb, km_meta)
    section2 = _build_per_leaf(by_leaf, km_meta)
    section3 = _build_per_credit_band(by_credit)
    section4 = _build_divergence_analysis(investigations)
    section5 = _build_seasoning_section(seasoning_df)
    section6 = _build_conclusion(df, wt_avg, seasoning_df, investigations)

    return _assemble_page(now, section1, section2, section3, section4, section5, section6)


# ---------------------------------------------------------------------------
# KM Metadata Loader
# ---------------------------------------------------------------------------
def _load_km_metadata(registry=None):
    """Extract KM provenance info from tree structure and segmentation metadata."""
    import json

    meta = {
        "n_total": 0,
        "n_fnba": 0,
        "n_freddie": 0,
        "n_leaves": 0,
        "features": [],
        "includes_censored": True,
        "fnba_source": "fnbaYear.xlsx",
        "freddie_source": "Freddie Mac Single-Family Loan-Level Dataset",
        "freddie_sample_frac": 0.10,
        "max_depth": 11,
        "curve_months": 360,
    }

    # Try segmentation_metadata.json first (has data source details)
    seg_meta_path = MODEL_DIR / "segmentation" / "segmentation_metadata.json"
    if seg_meta_path.is_file():
        try:
            seg_meta = json.loads(seg_meta_path.read_text())
            ds = seg_meta.get("data_sources", {})
            if "fnba" in ds:
                meta["n_fnba"] = ds["fnba"].get("n_loans", 0)
                meta["fnba_source"] = ds["fnba"].get("path", meta["fnba_source"])
            if "freddie" in ds:
                meta["n_freddie"] = ds["freddie"].get("n_loans", 0)
                meta["freddie_sample_frac"] = ds["freddie"].get("sample_fraction", 0.10)
            meta["includes_censored"] = seg_meta.get("includes_censored", True)
            meta["features"] = seg_meta.get("features", [])
            tc = seg_meta.get("tree_config", {})
            meta["n_leaves"] = tc.get("max_leaf_nodes", 75)
        except Exception:
            pass

    # Supplement from tree_structure.json (has per-leaf counts)
    reg = registry or ModelRegistry.get()
    ts = reg.tree_structure
    leaves = ts.get("leaves", [])
    if leaves:
        meta["n_leaves"] = len(leaves)
        if meta["n_fnba"] == 0:
            meta["n_fnba"] = sum(l.get("n_fnba", 0) for l in leaves)
        if meta["n_freddie"] == 0:
            meta["n_freddie"] = sum(l.get("n_freddie", 0) for l in leaves)
        # Build per-leaf composition for section 2
        meta["leaf_composition"] = {
            l["leaf_id"]: {
                "n_fnba": l.get("n_fnba", 0),
                "n_freddie": l.get("n_freddie", 0),
                "samples": l.get("samples", 0),
                "median_time": l.get("median_time"),
                "mean_time": l.get("mean_time"),
            }
            for l in leaves
        }

    meta["n_total"] = meta["n_fnba"] + meta["n_freddie"]
    if not meta["features"]:
        meta["features"] = ts.get("feature_names", [])

    return meta


# ---------------------------------------------------------------------------
# Methodology Box (KM provenance for management)
# ---------------------------------------------------------------------------
def _build_methodology_box(km_meta):
    if not km_meta or km_meta["n_total"] == 0:
        return ""

    n_total = km_meta["n_total"]
    n_fnba = km_meta["n_fnba"]
    n_freddie = km_meta["n_freddie"]
    n_leaves = km_meta["n_leaves"]
    freddie_pct = n_freddie / n_total * 100 if n_total else 0
    fnba_pct = n_fnba / n_total * 100 if n_total else 0
    freddie_full = n_freddie / km_meta["freddie_sample_frac"] if km_meta["freddie_sample_frac"] > 0 else n_freddie
    censored_note = " including both paid-off and still-active (censored) loans" if km_meta["includes_censored"] else ""

    feature_labels = {
        "noteDateYear": "Vintage Year",
        "creditScore": "Credit Score",
        "dti": "DTI",
        "ltv": "LTV",
        "interestRate": "Interest Rate",
        "loanSize": "Loan Size",
        "stateGroup": "State Group",
        "ITIN": "ITIN Flag",
        "origCustAmortMonth": "Orig Amort Term",
    }
    features = km_meta.get("features", [])
    feature_str = ", ".join(feature_labels.get(f, f) for f in features) if features else "9 loan characteristics"

    return f"""
    <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-left:4px solid #16a34a;border-radius:10px;padding:20px;margin-bottom:20px">
      <div style="font-size:16px;font-weight:700;margin-bottom:12px">Where Do the KM Survival Curves Come From?</div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:16px">
        <div style="background:white;border-radius:8px;padding:16px;border:1px solid #e5e7eb">
          <div style="font-size:11px;text-transform:uppercase;color:#6b7280;letter-spacing:0.5px;margin-bottom:4px">APEX2 (Production Model)</div>
          <div style="font-size:14px;line-height:1.6">
            FNBA&rsquo;s existing prepayment model. Uses <strong>4 lookup tables</strong>
            (credit score, rate delta, LTV, loan size) to produce a prepayment speed multiplier
            per loan. Applied to scheduled amortization to project when each loan pays off.
            The tables are calibrated to FNBA&rsquo;s historical portfolio.
          </div>
        </div>
        <div style="background:white;border-radius:8px;padding:16px;border:1px solid #e5e7eb">
          <div style="font-size:11px;text-transform:uppercase;color:#6b7280;letter-spacing:0.5px;margin-bottom:4px">KM Survival Curves (Data-Driven)</div>
          <div style="font-size:14px;line-height:1.6">
            Built from <strong>{n_total:,} actual loan outcomes</strong>{censored_note}.
            A decision tree groups loans into {n_leaves} segments based on similar characteristics,
            then Kaplan-Meier survival analysis within each segment measures how quickly loans
            actually paid off, month by month, over a 30-year horizon.
          </div>
        </div>
      </div>

      <div style="font-size:14px;line-height:1.7;margin-bottom:16px">
        <strong>Training Data Composition:</strong>
      </div>
      <div style="display:flex;gap:16px;margin-bottom:16px;flex-wrap:wrap">
        <div style="background:white;border-radius:8px;padding:14px 18px;border:1px solid #e5e7eb;flex:1;min-width:200px">
          <div style="font-size:22px;font-weight:700;color:#005C3F">{n_fnba:,}</div>
          <div style="font-size:12px;color:#6b7280">FNBA Internal Loans ({fnba_pct:.1f}%)</div>
          <div style="font-size:11px;color:#9ca3af;margin-top:4px">From {km_meta['fnba_source']} &mdash; includes ITIN and non-QM populations</div>
        </div>
        <div style="background:white;border-radius:8px;padding:14px 18px;border:1px solid #e5e7eb;flex:1;min-width:200px">
          <div style="font-size:22px;font-weight:700;color:#005C3F">{n_freddie:,}</div>
          <div style="font-size:12px;color:#6b7280">Freddie Mac Loans ({freddie_pct:.1f}%)</div>
          <div style="font-size:11px;color:#9ca3af;margin-top:4px">10% sample of {freddie_full:,.0f} conforming loans &mdash; provides broad rate/vintage coverage</div>
        </div>
        <div style="background:white;border-radius:8px;padding:14px 18px;border:1px solid #e5e7eb;flex:1;min-width:200px">
          <div style="font-size:22px;font-weight:700;color:#005C3F">{n_leaves}</div>
          <div style="font-size:12px;color:#6b7280">Segments (Tree Leaves)</div>
          <div style="font-size:11px;color:#9ca3af;margin-top:4px">Each tape loan is assigned to one segment with its own survival curve</div>
        </div>
      </div>

      <div style="font-size:14px;line-height:1.7;margin-bottom:8px">
        <strong>How Each Tape Loan Gets a Curve:</strong>
        The segmentation tree splits loans based on {feature_str}. Each of the {n_leaves} terminal
        segments (leaves) groups loans with similar payoff behavior. The Kaplan-Meier estimator then
        builds a month-by-month survival curve for each segment &mdash; &ldquo;what fraction of loans that
        entered this segment were still active at month 1, month 2, &hellip; month 360?&rdquo; Each tape loan
        is routed through the tree to its matching segment, inheriting that segment&rsquo;s empirical
        survival curve.
      </div>
      <div style="font-size:12px;color:#6b7280;line-height:1.6">
        <strong>KM life metrics explained:</strong>
        <strong>50%-Life</strong> = the month when half the training loans in that segment had paid off (a median).
        <strong>Mean Life</strong> = the area under the survival curve (an average that accounts for the full curve shape).
        <strong>Remaining Life</strong> = given that a loan has already survived to its current age, how many more months until
        50% of similar survivors pay off? This conditions on seasoning and is the most relevant for pricing seasoned loans.
      </div>
    </div>"""


# ---------------------------------------------------------------------------
# Section 1: Executive Summary
# ---------------------------------------------------------------------------
def _build_executive_summary(df, wt_avg, total_upb, km_meta=None):
    n_loans = len(df)
    has_tape_plug = "apex2_amort_plug" in df.columns and df["apex2_amort_plug"].notna().any()

    avg_apex2_life = wt_avg(df["apex2_proj_tape"])
    avg_km_50 = wt_avg(df["km_50pct_life"])
    avg_km_mean = wt_avg(df["km_mean_life"])
    avg_km_rem = wt_avg(df["km_remaining_life"])
    avg_seasoning = wt_avg(df["seasoning"])
    avg_rate = wt_avg(df["rate"])
    avg_credit = wt_avg(df["credit"])
    n_flagged = df["divergence_flag"].sum()
    pct_flagged = n_flagged / n_loans * 100

    tape_plug = wt_avg(df["apex2_amort_plug"]) if has_tape_plug else avg_apex2_life
    life_gap = avg_apex2_life - avg_km_50
    life_gap_pct = abs(life_gap) / avg_apex2_life * 100 if avg_apex2_life > 0 else 0

    # Traffic lights
    gap_color = "green" if abs(life_gap) <= 12 else ("yellow" if abs(life_gap) <= 24 else "red")
    flag_color = "green" if pct_flagged <= 10 else ("yellow" if pct_flagged <= 30 else "red")
    rate_delta = avg_rate - TREASURY_10Y
    rate_color = "green" if rate_delta >= -1 else ("yellow" if rate_delta >= -2 else "red")

    return f"""
    <div class="summary-grid">
      <div class="summary-card">
        <div class="card-number">{n_loans}</div>
        <div class="card-label">Loans</div>
      </div>
      <div class="summary-card">
        <div class="card-number">${total_upb:,.0f}</div>
        <div class="card-label">Total UPB</div>
      </div>
      <div class="summary-card">
        <div class="card-number">{avg_rate:.2f}%</div>
        <div class="card-label">Wtd Avg Rate</div>
      </div>
      <div class="summary-card">
        <div class="card-number">{avg_credit:.0f}</div>
        <div class="card-label">Wtd Avg Credit</div>
      </div>
    </div>

    <h2 class="section-title">1. Executive Summary</h2>
    <p class="section-hint">Portfolio-level APEX2 vs KM headline comparison with rate environment context.</p>

    <div class="metrics-grid">
      <div>
        <table class="data-table">
          <thead><tr><th>Life Estimate</th><th class="num">Months</th><th class="num">Years</th></tr></thead>
          <tbody>
            <tr><td>APEX2 Projected (tape mult, seasoned)</td><td class="num">{avg_apex2_life:.0f}</td><td class="num">{avg_apex2_life/12:.1f}</td></tr>
            <tr><td>KM 50%-Life (unconditional)</td><td class="num">{avg_km_50:.0f}</td><td class="num">{avg_km_50/12:.1f}</td></tr>
            <tr><td>KM Mean Life (area under curve)</td><td class="num">{avg_km_mean:.0f}</td><td class="num">{avg_km_mean/12:.1f}</td></tr>
            <tr><td>KM Remaining Life (conditioned on age)</td><td class="num">{avg_km_rem:.0f}</td><td class="num">{avg_km_rem/12:.1f}</td></tr>
            <tr style="font-weight:600;border-top:2px solid #e5e7eb"><td>Gap (APEX2 &minus; KM 50%)</td><td class="num">{life_gap:+.0f}</td><td class="num">{life_gap/12:+.1f}</td></tr>
          </tbody>
        </table>
      </div>
      <div>
        <div class="traffic-lights">
          <div class="traffic-light">
            <span class="badge badge-{gap_color}" style="min-width:60px;text-align:center">{life_gap:+.0f}mo</span>
            <div><div class="tl-value">Life Gap</div><div class="tl-label">APEX2 vs KM 50%-Life ({"|" if abs(life_gap) <= 12 else ">"} 12mo = green)</div></div>
          </div>
          <div class="traffic-light">
            <span class="badge badge-{flag_color}" style="min-width:60px;text-align:center">{pct_flagged:.0f}%</span>
            <div><div class="tl-value">Divergent Loans</div><div class="tl-label">&gt;24mo divergence ({n_flagged:.0f} of {n_loans})</div></div>
          </div>
          <div class="traffic-light">
            <span class="badge badge-{rate_color}" style="min-width:60px;text-align:center">{rate_delta:+.1f}%</span>
            <div><div class="tl-value">Rate Environment</div><div class="tl-label">Avg note rate {avg_rate:.2f}% vs 10Y Treasury {TREASURY_10Y}%</div></div>
          </div>
        </div>
      </div>
    </div>

    <div style="background:white;border:1px solid #e5e7eb;border-radius:10px;padding:16px;margin-bottom:20px">
      <strong>Rate Environment Context:</strong> The tape&rsquo;s weighted-average note rate is {avg_rate:.2f}%
      vs the current 10-year Treasury at {TREASURY_10Y}%. A rate delta of {rate_delta:+.1f}% means these
      loans are {"below market &mdash; borrowers have zero refinancing incentive, extending effective life"
      if rate_delta < -0.5 else "near market &mdash; refinancing incentive is moderate"
      if rate_delta < 0.5 else "above market &mdash; borrowers have refinancing incentive, shortening effective life"}.
      Average seasoning is {avg_seasoning:.0f} months ({avg_seasoning/12:.1f} years).
    </div>

    {_build_methodology_box(km_meta)}"""


# ---------------------------------------------------------------------------
# Section 2: Per-Leaf Comparison
# ---------------------------------------------------------------------------
def _build_per_leaf(by_leaf, km_meta=None):
    leaf_comp = km_meta.get("leaf_composition", {}) if km_meta else {}

    rows = []
    for _, r in by_leaf.iterrows():
        lid = int(r["leaf_id"])
        div = r["divergence_months"]
        div_class = "green" if abs(div) <= 12 else ("yellow" if abs(div) <= 24 else "red")

        # Training data composition for this leaf
        comp = leaf_comp.get(lid, {})
        train_total = comp.get("samples", 0)
        train_fnba = comp.get("n_fnba", 0)
        train_freddie = comp.get("n_freddie", 0)
        fnba_pct = train_fnba / train_total * 100 if train_total > 0 else 0

        rows.append(f"""
        <tr>
          <td class="num">{lid}</td>
          <td class="num">{int(r['count'])}</td>
          <td class="num">${r['upb']:,.0f}</td>
          <td class="num">{train_total:,}</td>
          <td class="num">{fnba_pct:.1f}%</td>
          <td class="num">{r['apex2_proj_tape']:.0f}</td>
          <td class="num">{r['km_50pct_life']:.0f}</td>
          <td class="num">{r['km_mean_life']:.0f}</td>
          <td class="num">{r['km_remaining_life']:.0f}</td>
          <td class="num"><span class="badge badge-{div_class}">{div:+.0f}mo</span></td>
        </tr>""")

    # Bar chart
    max_life = max(
        by_leaf["apex2_proj_tape"].max(),
        by_leaf["km_50pct_life"].max(),
        by_leaf["km_mean_life"].max(),
        1,
    )
    bar_rows = []
    for _, r in by_leaf.iterrows():
        lid = int(r["leaf_id"])
        n = int(r["count"])
        upb = r["upb"]
        comp = leaf_comp.get(lid, {})
        train_n = comp.get("samples", 0)
        apex2_w = r["apex2_proj_tape"] / max_life * 100
        km50_w = r["km_50pct_life"] / max_life * 100
        kmmean_w = r["km_mean_life"] / max_life * 100
        bar_rows.append(f"""
        <div class="life-bar-group">
          <div class="life-bar-label">Leaf {lid} <span class="muted">({n} tape loans, ${upb:,.0f} &middot; KM curve from {train_n:,} training loans)</span></div>
          <div class="life-bar-row"><span class="life-bar-tag">APEX2</span><div class="life-bar-track"><div class="life-bar-fill" style="width:{apex2_w:.0f}%;background:#f59e0b"></div></div><span class="life-bar-val">{r['apex2_proj_tape']:.0f}mo</span></div>
          <div class="life-bar-row"><span class="life-bar-tag">KM 50%</span><div class="life-bar-track"><div class="life-bar-fill" style="width:{km50_w:.0f}%;background:#005C3F"></div></div><span class="life-bar-val">{r['km_50pct_life']:.0f}mo</span></div>
          <div class="life-bar-row"><span class="life-bar-tag">Mean</span><div class="life-bar-track"><div class="life-bar-fill" style="width:{kmmean_w:.0f}%;background:#16a34a"></div></div><span class="life-bar-val">{r['km_mean_life']:.0f}mo</span></div>
        </div>""")

    return f"""
    <h2 class="section-title">2. Per-Leaf Comparison</h2>
    <p class="section-hint">Balance-weighted average effective life by segmentation tree leaf. Each leaf groups loans with similar risk characteristics.
    &ldquo;Training Loans&rdquo; is the number of historical loans used to build each leaf&rsquo;s KM survival curve. &ldquo;% FNBA&rdquo; shows how much
    of each leaf&rsquo;s curve comes from FNBA internal data vs Freddie Mac conforming loans.</p>

    <div class="table-wrap">
    <table class="data-table">
      <thead><tr>
        <th>Leaf</th><th>Tape Loans</th><th>Tape UPB</th>
        <th>Training Loans</th><th>% FNBA</th>
        <th>APEX2</th><th>KM 50%</th><th>KM Mean</th><th>KM Remain</th>
        <th>Divergence</th>
      </tr></thead>
      <tbody>{"".join(rows)}</tbody>
    </table>
    </div>

    <h3 class="subsection">Effective Life by Leaf &mdash; Three Methods</h3>
    <div class="chart-container">
      <div class="life-bars-container">
        {"".join(bar_rows)}
      </div>
      <div style="font-size:11px;color:#9ca3af;margin-top:8px">
        <span style="color:#f59e0b">&#9632;</span> APEX2 Projected (tape mult, seasoned) &nbsp;
        <span style="color:#005C3F">&#9632;</span> KM 50%-Life (unconditional) &nbsp;
        <span style="color:#16a34a">&#9632;</span> KM Mean Life (area under curve)
      </div>
    </div>"""


# ---------------------------------------------------------------------------
# Section 3: Per-Credit-Band Comparison
# ---------------------------------------------------------------------------
def _build_per_credit_band(by_credit):
    rows = []
    max_upb = by_credit["upb"].max() or 1
    for _, r in by_credit.iterrows():
        band = r["credit_band"]
        div = r["divergence_months"]
        div_class = "green" if abs(div) <= 12 else ("yellow" if abs(div) <= 24 else "red")
        bar_w = r["upb"] / max_upb * 100
        rows.append(f"""
        <tr>
          <td>{band}</td>
          <td class="num">{int(r['count'])}</td>
          <td class="num">${r['upb']:,.0f}</td>
          <td><div class="bar-bg"><div class="bar" style="width:{bar_w:.0f}%"></div></div></td>
          <td class="num">{r['apex2_proj_tape']:.0f}</td>
          <td class="num">{r['km_50pct_life']:.0f}</td>
          <td class="num">{r['km_mean_life']:.0f}</td>
          <td class="num">{r['km_remaining_life']:.0f}</td>
          <td class="num"><span class="badge badge-{div_class}">{div:+.0f}mo</span></td>
        </tr>""")

    # Bar chart by credit band
    max_life = max(
        by_credit["apex2_proj_tape"].max(),
        by_credit["km_50pct_life"].max(),
        by_credit["km_mean_life"].max(),
        1,
    )
    bar_rows = []
    for _, r in by_credit.iterrows():
        band = r["credit_band"]
        n = int(r["count"])
        apex2_w = r["apex2_proj_tape"] / max_life * 100
        km50_w = r["km_50pct_life"] / max_life * 100
        kmmean_w = r["km_mean_life"] / max_life * 100
        bar_rows.append(f"""
        <div class="life-bar-group">
          <div class="life-bar-label">{band} <span class="muted">({n} loans)</span></div>
          <div class="life-bar-row"><span class="life-bar-tag">APEX2</span><div class="life-bar-track"><div class="life-bar-fill" style="width:{apex2_w:.0f}%;background:#f59e0b"></div></div><span class="life-bar-val">{r['apex2_proj_tape']:.0f}mo</span></div>
          <div class="life-bar-row"><span class="life-bar-tag">KM 50%</span><div class="life-bar-track"><div class="life-bar-fill" style="width:{km50_w:.0f}%;background:#005C3F"></div></div><span class="life-bar-val">{r['km_50pct_life']:.0f}mo</span></div>
          <div class="life-bar-row"><span class="life-bar-tag">Mean</span><div class="life-bar-track"><div class="life-bar-fill" style="width:{kmmean_w:.0f}%;background:#16a34a"></div></div><span class="life-bar-val">{r['km_mean_life']:.0f}mo</span></div>
        </div>""")

    return f"""
    <h2 class="section-title">3. Per-Credit-Band Comparison</h2>
    <p class="section-hint">APEX2 credit score is the dominant pricing dimension. This view shows how life estimates differ across the 9 APEX2 credit bands.</p>

    <div class="table-wrap">
    <table class="data-table">
      <thead><tr>
        <th>Credit Band</th><th>Loans</th><th>UPB</th><th></th>
        <th>APEX2 Tape</th><th>KM 50%</th><th>KM Mean</th><th>KM Remain</th>
        <th>Divergence</th>
      </tr></thead>
      <tbody>{"".join(rows)}</tbody>
    </table>
    </div>

    <h3 class="subsection">Effective Life by Credit Band &mdash; Three Methods</h3>
    <div class="chart-container">
      <div class="life-bars-container">
        {"".join(bar_rows)}
      </div>
      <div style="font-size:11px;color:#9ca3af;margin-top:8px">
        <span style="color:#f59e0b">&#9632;</span> APEX2 Projected &nbsp;
        <span style="color:#005C3F">&#9632;</span> KM 50%-Life &nbsp;
        <span style="color:#16a34a">&#9632;</span> KM Mean Life
      </div>
    </div>"""


# ---------------------------------------------------------------------------
# Section 4: Divergence Analysis
# ---------------------------------------------------------------------------
def _build_divergence_analysis(investigations):
    if not investigations:
        return """
        <h2 class="section-title">4. Divergence Analysis</h2>
        <p class="section-hint">Segments where APEX2 and KM differ by more than 24 months.</p>
        <div style="background:var(--green-light);border:1px solid #bbf7d0;border-radius:10px;padding:20px;text-align:center">
          <strong>No segments with &gt;24-month divergence.</strong> All leaves have reasonable agreement between APEX2 and KM estimates.
        </div>"""

    cards = []
    for inv in investigations:
        leaf_id = inv["leaf_id"]
        avg_div = inv["avg_divergence"]
        div_sign = "longer" if avg_div > 0 else "shorter"

        # Rate delta distribution
        rd_rows = []
        for band, pct in sorted(inv["rate_delta_dist"].items(), key=lambda x: -x[1]):
            bar_w = pct
            rd_rows.append(f"""
            <tr><td>{band}</td><td class="num">{pct:.0f}%</td>
            <td><div class="bar-bg" style="width:120px"><div class="bar" style="width:{bar_w:.0f}%"></div></div></td></tr>""")

        # APEX2 dimension breakdown
        dim_rows = []
        for dim_name, dim_val in inv["apex2_dims"].items():
            label = dim_name.replace("dim_", "").replace("_", " ").title()
            dim_rows.append(f'<tr><td>{label}</td><td class="num">{dim_val:.3f}</td></tr>')

        pop = inv["population"]
        cards.append(f"""
        <div class="leaf-panel" style="border-left:4px solid var(--red)">
          <div class="leaf-panel-header">
            <span class="leaf-id-tag">Leaf {leaf_id}</span>
            <span class="badge badge-red">{avg_div:+.0f}mo divergence</span>
            <span class="leaf-stats">{inv['count']} loans &middot; ${inv['upb']:,.0f} UPB</span>
          </div>
          <p style="margin-bottom:12px">APEX2 estimates these loans live <strong>{abs(avg_div):.0f} months {div_sign}</strong> than KM historical data suggests.</p>
          <div class="leaf-panel-body">
            <div>
              <h4 style="font-size:12px;text-transform:uppercase;color:var(--gray-600);margin-bottom:8px">Rate Delta Distribution</h4>
              <table class="data-table" style="font-size:12px">
                <thead><tr><th>Band</th><th>% UPB</th><th></th></tr></thead>
                <tbody>{"".join(rd_rows)}</tbody>
              </table>
            </div>
            <div>
              <h4 style="font-size:12px;text-transform:uppercase;color:var(--gray-600);margin-bottom:8px">APEX2 Dimension Multipliers</h4>
              <table class="data-table" style="font-size:12px">
                <thead><tr><th>Dimension</th><th>Avg Mult</th></tr></thead>
                <tbody>{"".join(dim_rows)}</tbody>
              </table>
              <h4 style="font-size:12px;text-transform:uppercase;color:var(--gray-600);margin:12px 0 8px">Population Characteristics</h4>
              <table class="data-table" style="font-size:12px">
                <tbody>
                  <tr><td>Avg Credit</td><td class="num">{pop['avg_credit']:.0f}</td></tr>
                  <tr><td>Avg Rate</td><td class="num">{pop['avg_rate']:.2f}%</td></tr>
                  <tr><td>Avg LTV</td><td class="num">{pop['avg_ltv']:.1f}%</td></tr>
                  <tr><td>Avg Seasoning</td><td class="num">{pop['avg_seasoning']:.0f}mo</td></tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>""")

    return f"""
    <h2 class="section-title">4. Divergence Analysis</h2>
    <p class="section-hint">Detailed investigation of segments where APEX2 and KM differ by more than 24 months. Rate-delta band distribution explains why APEX2 may overestimate prepayment speed for below-market-rate loans.</p>
    {"".join(cards)}"""


# ---------------------------------------------------------------------------
# Section 5: Seasoning-Adjusted Comparison
# ---------------------------------------------------------------------------
def _build_seasoning_section(seasoning_df):
    rows = []
    for _, r in seasoning_df.iterrows():
        age = int(r["age"])
        gap = r["gap_months"]
        gap_class = "green" if abs(gap) <= 12 else ("yellow" if abs(gap) <= 24 else "red")
        rows.append(f"""
        <tr>
          <td class="num">{age}</td>
          <td class="num">{age/12:.1f}</td>
          <td class="num">{r['apex2_life']:.0f}</td>
          <td class="num">{r['km_remaining_life']:.0f}</td>
          <td class="num"><span class="badge badge-{gap_class}">{gap:+.0f}mo</span></td>
        </tr>""")

    # Line-style bar chart showing gap at each age
    max_gap = seasoning_df["gap_months"].abs().max() or 1
    gap_bars = []
    for _, r in seasoning_df.iterrows():
        age = int(r["age"])
        gap = r["gap_months"]
        bar_pct = abs(gap) / max_gap * 100
        color = "#f59e0b" if gap > 0 else "#005C3F"
        label = f"{gap:+.0f}mo"
        gap_bars.append(f"""
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
          <span style="width:50px;text-align:right;font-size:12px;color:var(--gray-600)">{age}mo</span>
          <div style="flex:1;height:14px;background:var(--gray-100);border-radius:3px;overflow:hidden">
            <div style="height:100%;width:{bar_pct:.0f}%;background:{color};border-radius:3px"></div>
          </div>
          <span style="width:60px;font-size:12px;font-weight:600">{label}</span>
        </div>""")

    return f"""
    <h2 class="section-title">5. Seasoning-Adjusted Comparison</h2>
    <p class="section-hint">How the APEX2 vs KM gap changes when conditioning on different loan ages. APEX2 uses a 30-month seasoning ramp; KM uses conditional survival (given the loan survived to age X, how much longer until 50% pay off?).</p>

    <div class="table-wrap">
    <table class="data-table">
      <thead><tr>
        <th>Age (mo)</th><th>Age (yr)</th>
        <th>APEX2 Life</th><th>KM Remaining</th><th>Gap</th>
      </tr></thead>
      <tbody>{"".join(rows)}</tbody>
    </table>
    </div>

    <h3 class="subsection">Gap by Assumed Loan Age</h3>
    <div class="chart-container">
      <div style="max-width:600px;margin:0 auto">
        {"".join(gap_bars)}
      </div>
      <div style="font-size:11px;color:#9ca3af;margin-top:8px">
        <span style="color:#f59e0b">&#9632;</span> APEX2 projects longer life &nbsp;
        <span style="color:#005C3F">&#9632;</span> KM projects longer remaining life
      </div>
    </div>"""


# ---------------------------------------------------------------------------
# Section 6: Conclusion
# ---------------------------------------------------------------------------
def _build_conclusion(df, wt_avg, seasoning_df, investigations):
    avg_apex2 = wt_avg(df["apex2_proj_tape"])
    avg_km_50 = wt_avg(df["km_50pct_life"])
    avg_km_rem = wt_avg(df["km_remaining_life"])
    avg_rate = wt_avg(df["rate"])
    avg_seasoning = wt_avg(df["seasoning"])
    n_flagged = df["divergence_flag"].sum()
    n_loans = len(df)

    gap = avg_apex2 - avg_km_50
    gap_rem = avg_apex2 - avg_km_rem
    rate_delta = avg_rate - TREASURY_10Y

    # Determine recommendation
    if abs(gap) <= 12:
        overall_assessment = "green"
        summary = "APEX2 and KM survival curves are in reasonable agreement."
        recommendation = "Both models produce similar effective life estimates. APEX2 can be used with confidence for pricing this tape."
    elif abs(gap) <= 24:
        overall_assessment = "yellow"
        summary = "Moderate divergence between APEX2 and KM survival curves."
        recommendation = "Consider using a blended estimate (midpoint of APEX2 and KM) or apply a conservative adjustment to APEX2 to account for the rate environment."
    else:
        overall_assessment = "red"
        if gap > 0:
            summary = f"APEX2 projects significantly longer lives than KM ({gap:+.0f} months). APEX2 may underestimate prepayment speed for this population."
            recommendation = "KM survival curves better capture the historical payoff behavior of similar loans. Recommend using KM-based estimates or applying a downward adjustment to APEX2 effective lives."
        else:
            summary = f"APEX2 projects significantly shorter lives than KM ({gap:+.0f} months). APEX2 may overestimate prepayment speed for this population."
            recommendation = "The below-market rate environment (rate delta {rate_delta:+.1f}%) suppresses refinancing. KM curves, trained on historical data including rate environments, better reflect expected behavior. Recommend using KM conditional remaining life ({avg_km_rem:.0f} months) as the primary estimate."

    # Build next steps
    next_steps = []
    if abs(gap) > 12:
        next_steps.append("Run sensitivity analysis on pricing using both APEX2 and KM life estimates to quantify dollar impact.")
    if rate_delta < -1:
        next_steps.append("Monitor rate environment: if Treasury rates fall significantly, these loans may develop refi incentive, shortening effective life toward APEX2 estimates.")
    if n_flagged > 0:
        next_steps.append(f"Investigate the {n_flagged} loans with >24-month divergence individually to assess if they represent systematic model disagreement or outlier characteristics.")
    next_steps.append("Consider replacing APEX2's static rate-delta bands with a forward-looking rate model that incorporates current yield curve shape.")

    next_steps_html = "\n".join(f"<li>{s}</li>" for s in next_steps)

    # Actual seasoning comparison
    actual_age = int(avg_seasoning)
    actual_row = seasoning_df[seasoning_df["age"].between(actual_age - 3, actual_age + 3)]
    if len(actual_row) > 0:
        nearest_row = actual_row.iloc[(actual_row["age"] - actual_age).abs().argsort().iloc[0]]
        seasoning_note = f"At the tape&rsquo;s actual average seasoning of {actual_age} months, the APEX2-KM gap is approximately {nearest_row['gap_months']:+.0f} months."
    else:
        seasoning_note = ""

    return f"""
    <h2 class="section-title">6. Conclusion &amp; Recommendation</h2>

    <div style="background:white;border:1px solid var(--gray-200);border-left:4px solid var(--{overall_assessment});border-radius:10px;padding:20px;margin-bottom:20px">
      <div style="font-size:18px;font-weight:700;margin-bottom:8px">
        <span class="badge badge-{overall_assessment}" style="font-size:14px">{overall_assessment.upper()}</span>
        &nbsp;{summary}
      </div>
      <p style="margin-bottom:12px">{recommendation}</p>
      {f'<p style="color:var(--gray-600);font-size:13px">{seasoning_note}</p>' if seasoning_note else ''}
    </div>

    <h3 class="subsection">Key Findings</h3>
    <ul style="margin:0 0 20px 20px;line-height:1.8">
      <li>Portfolio-level gap: APEX2 {avg_apex2:.0f}mo vs KM 50%-Life {avg_km_50:.0f}mo ({gap:+.0f}mo, {abs(gap)/avg_apex2*100 if avg_apex2 > 0 else 0:.0f}% difference)</li>
      <li>Seasoning-adjusted: APEX2 {avg_apex2:.0f}mo vs KM remaining life {avg_km_rem:.0f}mo ({gap_rem:+.0f}mo)</li>
      <li>Rate environment: avg note rate {avg_rate:.2f}% vs Treasury {TREASURY_10Y}% (delta {rate_delta:+.1f}%)</li>
      <li>{n_flagged} of {n_loans} loans ({n_flagged/n_loans*100:.0f}%) have &gt;24-month divergence</li>
    </ul>

    <h3 class="subsection">Next Steps</h3>
    <ol style="margin:0 0 20px 20px;line-height:1.8">
      {next_steps_html}
    </ol>"""


# ---------------------------------------------------------------------------
# Page Assembly
# ---------------------------------------------------------------------------
def _assemble_page(now, section1, section2, section3, section4, section5, section6):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Effective Life Comparison — APEX2 vs KM Survival</title>
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

  .leaf-panel {{
    background: white;
    border: 1px solid var(--gray-200);
    border-radius: 10px;
    padding: 20px;
    margin-bottom: 12px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  }}
  .leaf-panel-header {{
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 12px;
  }}
  .leaf-id-tag {{
    font-size: 16px;
    font-weight: 700;
    color: var(--blue);
  }}
  .leaf-panel-body {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
  }}

  .muted {{ color: var(--gray-400); font-style: italic; }}

  .footer {{
    text-align: center;
    color: var(--gray-400);
    font-size: 12px;
    margin-top: 40px;
    padding: 20px;
  }}
</style>
</head>
<body>
<div class="page">
  <div class="page-header">
    <h1>Effective Life Comparison</h1>
    <div class="subtitle">APEX2 vs KM Survival Curves &mdash; Generated {now}</div>
  </div>

  {section1}
  {section2}
  {section3}
  {section4}
  {section5}
  {section6}

  <div class="footer">
    Generated by Pricing Engine &mdash; {now}
  </div>
</div>

<script>
// Sortable table headers
document.querySelectorAll('.data-table thead th').forEach((th, colIdx) => {{
  let asc = true;
  th.addEventListener('click', () => {{
    const tbody = th.closest('table').querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    rows.sort((a, b) => {{
      const av = a.children[colIdx]?.textContent.replace(/[$,%,]/g, '').trim() || '';
      const bv = b.children[colIdx]?.textContent.replace(/[$,%,]/g, '').trim() || '';
      const an = parseFloat(av.replace(/,/g, ''));
      const bn = parseFloat(bv.replace(/,/g, ''));
      if (!isNaN(an) && !isNaN(bn)) return asc ? an - bn : bn - an;
      return asc ? av.localeCompare(bv) : bv.localeCompare(av);
    }});
    asc = !asc;
    rows.forEach(r => tbody.appendChild(r));
  }});
}});
</script>
</body>
</html>"""


# ===================================================================
# Main
# ===================================================================
def main():
    parser = argparse.ArgumentParser(description="Effective Life Comparison — APEX2 vs KM Survival")
    parser.add_argument("--tape", help="Path to Excel loan tape (default: loan_tape_2_clean.xlsx)")
    parser.add_argument("--out", help="Output HTML filename (default: effective_life_comparison.html)")
    args = parser.parse_args()

    tape_path = Path(args.tape) if args.tape else BACKEND_DIR / "loan_tape_2_clean.xlsx"
    if not tape_path.exists():
        logger.error("Tape not found: %s", tape_path)
        sys.exit(1)

    t_start = time.time()

    # Stage 1: Load
    df, pkg = stage_load(tape_path)

    # Stage 2: Init models
    registry = stage_init_models()

    # Stage 3: Compute per-loan lives
    df = stage_compute_lives(df, pkg)

    # Stage 4: Aggregate
    by_leaf, by_credit = stage_aggregate(df)

    # Stage 5: Seasoning sensitivity
    seasoning_df = stage_seasoning_sensitivity(df)

    # Stage 6: Divergence investigation
    investigations = stage_divergence_investigation(df)

    # Export CSV
    REPORTS_DIR.mkdir(exist_ok=True)
    csv_path = REPORTS_DIR / "effective_life_comparison.csv"
    export_csv(df, csv_path)

    # Build HTML
    html = build_html(df, by_leaf, by_credit, seasoning_df, investigations, registry=registry)

    out_name = args.out or "effective_life_comparison.html"
    html_path = REPORTS_DIR / out_name
    html_path.write_text(html, encoding="utf-8")

    logger.info("Wrote %s (%d KB)", html_path, len(html) // 1024)
    logger.info("Wrote %s", csv_path)
    logger.info("Total time: %.1fs", time.time() - t_start)


if __name__ == "__main__":
    main()
