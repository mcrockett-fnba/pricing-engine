#!/usr/bin/env python3
"""APEX2 Prepayment Model Comparison Tool.

Loads a loan tape, applies APEX2 dimensional prepayment multipliers,
and compares effective life under different assumptions:
  - APEX2 flat (amortization plug)
  - Monthly projection with constant-dollar prepay
  - Monthly projection with seasoning ramp
  - Credit-band-only vs blended multiplier

Usage:
    cd backend && python scripts/apex2_comparison.py [loan_tape.xlsx]

If no file is specified, defaults to loan_tape_2_clean.xlsx in the backend dir.
"""
import math
import sys
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
TREASURY_10Y = 4.5  # Current 10-year treasury rate (%)
SEASONING_RAMP_MONTHS = 30  # PSA-style linear ramp

# APEX2 Not-ITIN prepayment multipliers by credit band (from production data)
APEX2_CREDIT_RATES = {
    "<576": 1.3583,
    "576-600": 1.5713,
    "601-625": 1.8124,
    "626-650": 2.1814,
    "651-675": 2.4668,
    "676-700": 2.7220,
    "701-725": 2.7022,
    "726-750": 2.7284,
    ">=751": 2.7159,
}

# APEX2 Not-ITIN prepayment multipliers by rate delta band
APEX2_RATE_DELTA_RATES = {
    "<=-3%": 1.4307,
    "-2 to -2.99%": 1.2733,
    "-1 to -1.99%": 1.7116,
    "-0.99 to 0.99%": 1.8363,
    "1 to 1.99%": 2.0108,
    "2 to 2.99%": 2.4278,
    ">=3%": 2.3215,
}

# APEX2 Not-ITIN prepayment multipliers by LTV band
APEX2_LTV_RATES = {
    "< 75%": 2.2420,
    "75% - 79.99%": 2.5268,
    "80% - 84.99%": 2.5173,
    "85% - 89.99%": 2.0415,
    ">= 90%": 1.6916,
}

# APEX2 Not-ITIN prepayment multipliers by loan size band
APEX2_LOAN_SIZE_RATES = {
    "$0 - $49,999": 1.3169,
    "$50,000 - $99,999": 1.6846,
    "$100,000 - $149,999": 2.2964,
    "$150,000 - $199,999": 2.6937,
    "$200,000 - $249,999": 2.8286,
    "$250,000 - $499,999": 2.9982,
    "$500,000 - $999,999": 3.3578,
    "$1,000,000+": 3.3335,
}


# ---------------------------------------------------------------------------
# Band assignment functions
# ---------------------------------------------------------------------------
def get_credit_band(score: float) -> str:
    if score <= 575:
        return "<576"
    if score <= 600:
        return "576-600"
    if score <= 625:
        return "601-625"
    if score <= 650:
        return "626-650"
    if score <= 675:
        return "651-675"
    if score <= 700:
        return "676-700"
    if score <= 725:
        return "701-725"
    if score <= 750:
        return "726-750"
    return ">=751"


def get_rate_delta_band(rate_pct: float, treasury: float = TREASURY_10Y) -> str:
    delta = rate_pct - treasury
    if delta <= -3:
        return "<=-3%"
    if delta <= -2:
        return "-2 to -2.99%"
    if delta <= -1:
        return "-1 to -1.99%"
    if delta < 1:
        return "-0.99 to 0.99%"
    if delta < 2:
        return "1 to 1.99%"
    if delta < 3:
        return "2 to 2.99%"
    return ">=3%"


def get_ltv_band(ltv_pct: float) -> str:
    if ltv_pct < 75:
        return "< 75%"
    if ltv_pct < 80:
        return "75% - 79.99%"
    if ltv_pct < 85:
        return "80% - 84.99%"
    if ltv_pct < 90:
        return "85% - 89.99%"
    return ">= 90%"


def get_loan_size_band(balance: float) -> str:
    if balance < 50000:
        return "$0 - $49,999"
    if balance < 100000:
        return "$50,000 - $99,999"
    if balance < 150000:
        return "$100,000 - $149,999"
    if balance < 200000:
        return "$150,000 - $199,999"
    if balance < 250000:
        return "$200,000 - $249,999"
    if balance < 500000:
        return "$250,000 - $499,999"
    if balance < 1000000:
        return "$500,000 - $999,999"
    return "$1,000,000+"


def compute_apex2_multiplier(
    credit: float,
    rate_pct: float,
    ltv_pct: float,
    balance: float,
    treasury: float = TREASURY_10Y,
) -> dict:
    """Compute APEX2-style multiplier from available dimensions.

    Returns dict with per-dimension multipliers and averages.
    """
    dims = {}
    dims["dim_credit"] = APEX2_CREDIT_RATES.get(get_credit_band(credit), 2.0)
    dims["dim_rate_delta"] = APEX2_RATE_DELTA_RATES.get(
        get_rate_delta_band(rate_pct, treasury), 1.8
    )
    dims["dim_ltv"] = APEX2_LTV_RATES.get(get_ltv_band(ltv_pct), 2.2)
    dims["dim_loan_size"] = APEX2_LOAN_SIZE_RATES.get(
        get_loan_size_band(balance), 2.5
    )

    dims["avg_4dim"] = sum(dims.values()) / len(dims)
    dims["credit_only"] = dims["dim_credit"]
    return dims


# ---------------------------------------------------------------------------
# Projection functions
# ---------------------------------------------------------------------------
def seasoning_multiplier(age: float) -> float:
    if age <= 0:
        return 0.0
    return min(age / SEASONING_RAMP_MONTHS, 1.0)


def apex2_amortize(pv: float, pmt: float, rate_pct: float, ppy: int = 12):
    """Replicate utilities.Amortize — returns effective life in months."""
    r = rate_pct / ppy / 100
    if r <= 0 or pmt <= 0:
        return None
    ratio = pv * r / pmt
    if ratio >= 1:
        return None
    return math.ceil(-math.log(1 - ratio) / math.log(1 + r))


def project_effective_life(
    balance: float,
    pandi: float,
    rate_pct: float,
    multiplier: float,
    seasoning: float,
    remaining_term: int,
    use_seasoning: bool = True,
) -> int:
    """Monthly projection with constant-dollar prepay (APEX2-compatible).

    Returns effective life in months (when balance reaches ~0).
    """
    r = rate_pct / 12 / 100
    extra_base = pandi * max(multiplier - 1, 0)
    bal = balance
    for m in range(1, remaining_term + 1):
        if bal <= 1:
            return m - 1
        age = seasoning + m
        s = seasoning_multiplier(age) if use_seasoning else 1.0
        interest = bal * r
        sched = min(pandi, bal * (1 + r))
        principal = sched - interest
        extra = extra_base * s
        bal = max(bal - principal - extra, 0)
    return remaining_term


# ---------------------------------------------------------------------------
# Tape loading
# ---------------------------------------------------------------------------
def load_tape(path: str | Path) -> pd.DataFrame:
    """Load and clean a loan tape Excel file."""
    df = pd.read_excel(path)
    df.columns = [str(c).strip() for c in df.columns]

    # Drop empty / summary rows
    df = df[
        df["Current Balance"].notna()
        & (df["Current Balance"] > 0)
        & (df["Current Balance"] < 10_000_000)
    ].copy()

    # Find LTV column by partial match
    ltv_col = next(c for c in df.columns if "LTV used for Pricing" in c)

    df = df.rename(
        columns={
            "Current Balance": "balance",
            "Current Rate": "rate",
            "P&I for pricing": "pandi",
            "Seasoning": "seasoning",
            "FNBA Calculated Rem Term": "rem_term",
            "Most Recent Blended Credit Score for Pricing": "credit",
            ltv_col: "ltv",
            "Prepayment Rate": "apex2_prepay",
            "Amortization Plug": "apex2_amort_plug",
            "Cents on the Dollar": "cents_dollar",
            "Final Price with ITV Cap": "final_price",
            "Property State": "state",
            "Rate Type": "rate_type",
        }
    )

    required = ["balance", "rate", "pandi", "credit", "seasoning", "rem_term"]
    df = df.dropna(subset=required)
    return df


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------
def run_analysis(df: pd.DataFrame, treasury: float = TREASURY_10Y):
    w = df["balance"]
    total_upb = w.sum()

    def wt_avg(series):
        return (series * w).sum() / total_upb

    # --- Package summary ---
    print(f"\n{'=' * 72}")
    print(f"  PACKAGE SUMMARY ({len(df)} loans)")
    print(f"{'=' * 72}")
    print(f"Total UPB:           ${total_upb:>14,.0f}")
    if "final_price" in df.columns and df["final_price"].notna().any():
        print(f"Total Final Price:   ${df['final_price'].sum():>14,.0f}")
    if "cents_dollar" in df.columns and df["cents_dollar"].notna().any():
        print(f"Avg Cents/$:         {df['cents_dollar'].mean():>14.2f}")
    print(f"Wtd Avg Rate:        {wt_avg(df['rate']):>13.3f}%")
    print(f"Wtd Avg Credit:      {wt_avg(df['credit']):>14.0f}")
    if "ltv" in df.columns and df["ltv"].notna().any():
        print(f"Wtd Avg LTV:         {wt_avg(df['ltv']):>13.1f}%")
    print(f"Wtd Avg Seasoning:   {wt_avg(df['seasoning']):>10.1f} months")
    print(f"Wtd Avg Rem Term:    {wt_avg(df['rem_term']):>10.1f} months")
    print(f"Treasury (10Y):      {treasury:>13.2f}%")

    # --- APEX2 tape values ---
    has_apex2 = "apex2_prepay" in df.columns and df["apex2_prepay"].notna().any()
    if has_apex2:
        print(f"\n{'─' * 72}")
        print(f"  APEX2 VALUES (from tape)")
        print(f"{'─' * 72}")
        print(f"Wtd Avg Prepay Mult: {wt_avg(df['apex2_prepay']):>14.4f}")
        print(
            f"Min / Median / Max:  {df['apex2_prepay'].min():.4f} / "
            f"{df['apex2_prepay'].median():.4f} / {df['apex2_prepay'].max():.4f}"
        )
        wt_plug = wt_avg(df["apex2_amort_plug"])
        print(f"Wtd Avg Amort Plug:  {wt_plug:>10.1f} months ({wt_plug / 12:.1f} years)")

    # --- Compute multipliers ---
    mult_rows = []
    for _, row in df.iterrows():
        mult_rows.append(
            compute_apex2_multiplier(
                row["credit"],
                row["rate"],
                row.get("ltv", 60),
                row["balance"],
                treasury,
            )
        )
    for key in mult_rows[0]:
        df[key] = [m[key] for m in mult_rows]

    # --- Run projections ---
    scenarios = {}

    # For each multiplier source: tape (if available), 4-dim average, credit-only
    mult_sources = {"4-dim avg": "avg_4dim", "credit-only": "credit_only"}
    if has_apex2:
        mult_sources = {"tape (blended)": "apex2_prepay", **mult_sources}

    for label, mult_col in mult_sources.items():
        for seas_label, use_seas, override_age in [
            ("flat", False, None),
            ("seasoned (actual)", True, None),
            ("seasoned (age=0)", True, 0),
        ]:
            key = f"{label} / {seas_label}"
            lives = []
            plugs = []
            for _, loan in df.iterrows():
                mult = loan[mult_col]
                age = override_age if override_age is not None else loan["seasoning"]
                rem = int(loan["rem_term"])

                plug = apex2_amortize(
                    loan["balance"], loan["pandi"] * mult, loan["rate"], 12
                )
                life = project_effective_life(
                    loan["balance"],
                    loan["pandi"],
                    loan["rate"],
                    mult,
                    age,
                    rem,
                    use_seasoning=use_seas,
                )
                plugs.append(plug)
                lives.append(life)

            df[f"plug_{key}"] = plugs
            df[f"life_{key}"] = lives
            scenarios[key] = {
                "plug": (pd.Series(plugs) * w).sum() / total_upb,
                "life": (pd.Series(lives) * w).sum() / total_upb,
            }

    # --- Results table ---
    print(f"\n{'─' * 72}")
    print(f"  EFFECTIVE LIFE COMPARISON (balance-weighted, in months / years)")
    print(f"{'─' * 72}")
    print(f"{'Scenario':<42s} {'NPER':>8s} {'Monthly':>8s}")
    print(f"{'-' * 42} {'-' * 8} {'-' * 8}")
    for key, vals in scenarios.items():
        plug_str = f"{vals['plug']:.0f}m" if vals["plug"] else "n/a"
        life_str = f"{vals['life']:.0f}m"
        print(f"{key:<42s} {plug_str:>8s} {life_str:>8s}")

    print(f"\n{'Scenario':<42s} {'NPER':>8s} {'Monthly':>8s}")
    print(f"{'-' * 42} {'-' * 8} {'-' * 8}")
    for key, vals in scenarios.items():
        plug_str = f"{vals['plug'] / 12:.1f}y" if vals["plug"] else "n/a"
        life_str = f"{vals['life'] / 12:.1f}y"
        print(f"{key:<42s} {plug_str:>8s} {life_str:>8s}")

    # --- Credit band breakdown ---
    print(f"\n{'─' * 72}")
    print(f"  CREDIT BAND BREAKDOWN")
    print(f"{'─' * 72}")
    bins = [0, 575, 600, 625, 650, 675, 700, 725, 750, 1000]
    labels = [
        "<576", "576-600", "601-625", "626-650", "651-675",
        "676-700", "701-725", "726-750", ">=751",
    ]
    df["credit_band"] = pd.cut(df["credit"], bins=bins, labels=labels, right=True)
    print(
        f"{'Band':>10s} {'#':>4s} {'UPB':>14s} "
        f"{'Tape':>6s} {'4dim':>6s} {'Cred':>6s} {'Rate':>6s}"
    )
    print(f"{'-' * 10} {'-' * 4} {'-' * 14} {'-' * 6} {'-' * 6} {'-' * 6} {'-' * 6}")
    for band in labels:
        g = df[df["credit_band"] == band]
        if len(g) == 0:
            continue
        tape_str = f"{g['apex2_prepay'].mean():.3f}" if has_apex2 else "  n/a"
        print(
            f"{band:>10s} {len(g):>4d} ${g['balance'].sum():>12,.0f} "
            f"{tape_str:>6s} {g['avg_4dim'].mean():>6.3f} "
            f"{g['dim_credit'].mean():>6.3f} {g['rate'].mean():>5.2f}%"
        )

    # --- Seasoning sensitivity ---
    print(f"\n{'─' * 72}")
    print(f"  SEASONING SENSITIVITY")
    print(f"{'─' * 72}")
    avg_age = wt_avg(df["seasoning"])
    print(f"Actual avg seasoning: {avg_age:.0f} months (past {SEASONING_RAMP_MONTHS}mo ramp)")

    # Find the flat and age=0 scenarios for the first multiplier source
    first_mult = list(mult_sources.keys())[0]
    flat_key = f"{first_mult} / flat"
    seas_key = f"{first_mult} / seasoned (actual)"
    new_key = f"{first_mult} / seasoned (age=0)"

    if flat_key in scenarios and new_key in scenarios:
        flat_life = scenarios[flat_key]["life"]
        seas_life = scenarios[seas_key]["life"]
        new_life = scenarios[new_key]["life"]
        print(f"Impact on this package (actual age): {seas_life - flat_life:+.1f} months")
        print(f"Impact if package were brand new:    {new_life - flat_life:+.1f} months")
        if flat_life > 0:
            print(
                f"  → {(new_life / flat_life - 1) * 100:.1f}% longer effective life"
            )
            print(f"  → APEX2 would overprice a new-loan package by this margin")

    return df


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    backend_dir = Path(__file__).resolve().parent.parent
    if len(sys.argv) > 1:
        tape_path = Path(sys.argv[1])
    else:
        tape_path = backend_dir / "loan_tape_2_clean.xlsx"

    if not tape_path.exists():
        print(f"ERROR: Loan tape not found at {tape_path}")
        sys.exit(1)

    print(f"Loading tape: {tape_path.name}")
    df = load_tape(tape_path)
    print(f"Loaded {len(df)} loans")

    run_analysis(df)


if __name__ == "__main__":
    main()
