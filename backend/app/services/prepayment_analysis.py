"""APEX2 prepayment analysis service.

Computes effective life under different multiplier sources and projection
methods for a loan package, plus credit band breakdowns and seasoning
sensitivity.
"""
import math
from collections import defaultdict

from app.models.package import Package
from app.ml.model_loader import ModelRegistry
from app.models.prepayment import (
    CreditBandRow,
    LoanMultiplierDetail,
    PrepaymentAnalysisResult,
    PrepaymentConfig,
    PrepaymentSummary,
    RateCurveScenarioResult,
    ScenarioResult,
    SeasoningSensitivityPoint,
)

# ---------------------------------------------------------------------------
# APEX2 lookup tables — fallback values if registry has no loaded data
# ---------------------------------------------------------------------------
_FALLBACK_CREDIT_RATES = {
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

_FALLBACK_RATE_DELTA_RATES = {
    "<=-3%": 1.4307,
    "-2 to -2.99%": 1.2733,
    "-1 to -1.99%": 1.7116,
    "-0.99 to 0.99%": 1.8363,
    "1 to 1.99%": 2.0108,
    "2 to 2.99%": 2.4278,
    ">=3%": 2.3215,
}

_FALLBACK_LTV_RATES = {
    "< 75%": 2.2420,
    "75% - 79.99%": 2.5268,
    "80% - 84.99%": 2.5173,
    "85% - 89.99%": 2.0415,
    ">= 90%": 1.6916,
}

_FALLBACK_LOAN_SIZE_RATES = {
    "$0 - $49,999": 1.3169,
    "$50,000 - $99,999": 1.6846,
    "$100,000 - $149,999": 2.2964,
    "$150,000 - $199,999": 2.6937,
    "$200,000 - $249,999": 2.8286,
    "$250,000 - $499,999": 2.9982,
    "$500,000 - $999,999": 3.3578,
    "$1,000,000+": 3.3335,
}


def _get_apex2_tables() -> tuple[dict, dict, dict, dict]:
    """Return APEX2 lookup tables from the model registry, falling back to hardcoded values."""
    registry = ModelRegistry.get()
    tables = registry.apex2_tables
    return (
        tables.get("credit_rates", _FALLBACK_CREDIT_RATES),
        tables.get("rate_delta_rates", _FALLBACK_RATE_DELTA_RATES),
        tables.get("ltv_rates", _FALLBACK_LTV_RATES),
        tables.get("loan_size_rates", _FALLBACK_LOAN_SIZE_RATES),
    )


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


def get_rate_delta_band(rate_pct: float, treasury: float) -> str:
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
    treasury: float,
) -> dict:
    """Compute APEX2-style multiplier from available dimensions."""
    credit_rates, rate_delta_rates, ltv_rates, loan_size_rates = _get_apex2_tables()
    dims = {}
    dims["credit_band"] = get_credit_band(credit)
    dims["dim_credit"] = credit_rates.get(dims["credit_band"], 2.0)
    dims["rate_delta_band"] = get_rate_delta_band(rate_pct, treasury)
    dims["dim_rate_delta"] = rate_delta_rates.get(dims["rate_delta_band"], 1.8)
    dims["ltv_band"] = get_ltv_band(ltv_pct)
    dims["dim_ltv"] = ltv_rates.get(dims["ltv_band"], 2.2)
    dims["loan_size_band"] = get_loan_size_band(balance)
    dims["dim_loan_size"] = loan_size_rates.get(dims["loan_size_band"], 2.5)

    dim_values = [dims["dim_credit"], dims["dim_rate_delta"], dims["dim_ltv"], dims["dim_loan_size"]]
    dims["avg_4dim"] = sum(dim_values) / len(dim_values)
    dims["credit_only"] = dims["dim_credit"]
    return dims


# ---------------------------------------------------------------------------
# Projection functions
# ---------------------------------------------------------------------------
def seasoning_multiplier(age: float, ramp_months: int = 30) -> float:
    if age <= 0:
        return 0.0
    return min(age / ramp_months, 1.0)


def compute_pandi(balance: float, rate_pct: float, remaining_term: int) -> float:
    """Standard amortization P&I payment from loan fields.

    rate_pct is the annual rate in percent (e.g. 7.2).
    """
    r = rate_pct / 12 / 100
    if r <= 0 or remaining_term <= 0:
        return balance / max(remaining_term, 1)
    return balance * r / (1 - (1 + r) ** -remaining_term)


def apex2_amortize(pv: float, pmt: float, rate_pct: float, ppy: int = 12):
    """Replicate utilities.Amortize -- returns effective life in months."""
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
    ramp_months: int = 30,
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
        s = seasoning_multiplier(age, ramp_months) if use_seasoning else 1.0
        interest = bal * r
        sched = min(pandi, bal * (1 + r))
        principal = sched - interest
        extra = extra_base * s
        bal = max(bal - principal - extra, 0)
    return remaining_term


def interpolate_treasury(points: list[tuple[int, float]], month: int) -> float:
    """Linear interpolation of treasury rate from (month, rate) curve points.

    Flat extrapolation beyond endpoints.
    """
    if not points:
        return 4.5
    if len(points) == 1:
        return points[0][1]
    # Sort by month
    pts = sorted(points, key=lambda p: p[0])
    if month <= pts[0][0]:
        return pts[0][1]
    if month >= pts[-1][0]:
        return pts[-1][1]
    # Find surrounding points
    for i in range(len(pts) - 1):
        m0, r0 = pts[i]
        m1, r1 = pts[i + 1]
        if m0 <= month <= m1:
            if m1 == m0:
                return r0
            t = (month - m0) / (m1 - m0)
            return r0 + t * (r1 - r0)
    return pts[-1][1]


def project_effective_life_with_curve(
    balance: float,
    pandi: float,
    rate_pct: float,
    dim_credit: float,
    dim_ltv: float,
    dim_loan_size: float,
    treasury_curve: list[tuple[int, float]],
    seasoning: float,
    remaining_term: int,
    ramp_months: int = 30,
) -> int:
    """Monthly projection with time-varying APEX2 multiplier from a treasury curve.

    The rate delta dimension is recomputed each month based on the interpolated
    treasury rate.  The other 3 dimensions (credit, LTV, loan size) are fixed.

    Returns effective life in months.
    """
    _, rate_delta_rates, _, _ = _get_apex2_tables()
    r = rate_pct / 12 / 100
    bal = balance

    for m in range(1, remaining_term + 1):
        if bal <= 1:
            return m - 1
        age = seasoning + m
        s = seasoning_multiplier(age, ramp_months)

        # Time-varying rate delta dimension
        tsy = interpolate_treasury(treasury_curve, m)
        rd_band = get_rate_delta_band(rate_pct, tsy)
        dim_rate_delta = rate_delta_rates.get(rd_band, 1.8)

        multiplier = (dim_credit + dim_rate_delta + dim_ltv + dim_loan_size) / 4.0
        extra_base = pandi * max(multiplier - 1, 0)

        interest = bal * r
        sched = min(pandi, bal * (1 + r))
        principal = sched - interest
        extra = extra_base * s
        bal = max(bal - principal - extra, 0)
    return remaining_term


# ---------------------------------------------------------------------------
# Main analysis entry point
# ---------------------------------------------------------------------------
def run_prepayment_analysis(
    package: Package, config: PrepaymentConfig | None = None
) -> PrepaymentAnalysisResult:
    """Run full APEX2 prepayment analysis on a loan package."""
    cfg = config or PrepaymentConfig()
    treasury = cfg.treasury_10y
    ramp = cfg.seasoning_ramp_months

    # --- Per-loan computation ---
    loan_data = []
    for loan in package.loans:
        balance = loan.unpaid_balance
        rate_pct = loan.interest_rate * 100  # decimal -> percent
        ltv_pct = (loan.ltv or 0.80) * 100   # decimal -> percent
        credit = float(loan.credit_score or 700)
        age = loan.loan_age
        rem = loan.remaining_term

        pandi = compute_pandi(balance, rate_pct, rem)
        dims = compute_apex2_multiplier(credit, rate_pct, ltv_pct, balance, treasury)

        loan_data.append({
            "loan_id": loan.loan_id,
            "balance": balance,
            "rate_pct": rate_pct,
            "ltv_pct": ltv_pct,
            "credit": credit,
            "age": age,
            "rem": rem,
            "pandi": pandi,
            "dims": dims,
        })

    total_upb = sum(ld["balance"] for ld in loan_data)
    if total_upb == 0:
        total_upb = 1.0  # avoid div-by-zero

    def wtd_avg(key):
        return sum(ld[key] * ld["balance"] for ld in loan_data) / total_upb

    # --- Summary ---
    summary = PrepaymentSummary(
        loan_count=len(loan_data),
        total_upb=total_upb,
        wtd_avg_rate=wtd_avg("rate_pct"),
        wtd_avg_credit=wtd_avg("credit"),
        wtd_avg_ltv=wtd_avg("ltv_pct"),
        wtd_avg_seasoning=wtd_avg("age"),
        wtd_avg_remaining_term=wtd_avg("rem"),
        treasury_10y=treasury,
        wtd_avg_multiplier=round(
            sum(ld["dims"]["avg_4dim"] * ld["balance"] for ld in loan_data) / total_upb, 4
        ),
    )

    # --- Scenarios: {4-dim avg, credit-only} x {flat, seasoned actual, seasoned age=0} ---
    mult_sources = [
        ("4-dim avg", "avg_4dim"),
        ("credit-only", "credit_only"),
    ]
    methods = [
        ("Flat", False, None),
        ("Seasoned (actual age)", True, None),
        ("Seasoned (new, age=0)", True, 0),
    ]

    scenarios = []
    for src_label, src_key in mult_sources:
        for meth_label, use_seas, override_age in methods:
            nper_total = 0.0
            monthly_total = 0.0
            for ld in loan_data:
                mult = ld["dims"][src_key]
                age = override_age if override_age is not None else ld["age"]

                nper = apex2_amortize(ld["balance"], ld["pandi"] * mult, ld["rate_pct"])
                life = project_effective_life(
                    ld["balance"], ld["pandi"], ld["rate_pct"],
                    mult, age, ld["rem"],
                    use_seasoning=use_seas, ramp_months=ramp,
                )
                if nper is not None:
                    nper_total += nper * ld["balance"]
                monthly_total += life * ld["balance"]

            wtd_nper = nper_total / total_upb if nper_total > 0 else None
            wtd_monthly = monthly_total / total_upb

            scenarios.append(ScenarioResult(
                label=f"{src_label} / {meth_label}",
                multiplier_source=src_label,
                method=meth_label,
                nper_months=round(wtd_nper, 1) if wtd_nper is not None else None,
                monthly_months=round(wtd_monthly, 1),
                nper_years=round(wtd_nper / 12, 2) if wtd_nper is not None else None,
                monthly_years=round(wtd_monthly / 12, 2),
            ))

    # --- Credit band breakdown ---
    band_groups = defaultdict(list)
    for ld in loan_data:
        band = ld["dims"]["credit_band"]
        band_groups[band].append(ld)

    # Maintain canonical order
    credit_rates, _, _, _ = _get_apex2_tables()
    band_order = list(credit_rates.keys())
    credit_bands = []
    for band in band_order:
        group = band_groups.get(band, [])
        if not group:
            continue
        group_upb = sum(ld["balance"] for ld in group)
        avg_mult = sum(ld["dims"]["avg_4dim"] * ld["balance"] for ld in group) / group_upb
        avg_credit_mult = sum(ld["dims"]["credit_only"] * ld["balance"] for ld in group) / group_upb
        avg_rate = sum(ld["rate_pct"] * ld["balance"] for ld in group) / group_upb

        # Effective life using 4-dim avg, flat method
        eff_life_total = 0.0
        for ld in group:
            life = project_effective_life(
                ld["balance"], ld["pandi"], ld["rate_pct"],
                ld["dims"]["avg_4dim"], ld["age"], ld["rem"],
                use_seasoning=False, ramp_months=ramp,
            )
            eff_life_total += life * ld["balance"]
        eff_life = eff_life_total / group_upb

        credit_bands.append(CreditBandRow(
            band=band,
            loan_count=len(group),
            total_upb=group_upb,
            avg_multiplier=round(avg_mult, 4),
            avg_credit_multiplier=round(avg_credit_mult, 4),
            avg_rate=round(avg_rate, 3),
            effective_life_months=round(eff_life, 1),
        ))

    # --- Seasoning sensitivity ---
    sensitivity = []
    for assumed_age in range(0, 61, 6):
        life_total = 0.0
        for ld in loan_data:
            mult = ld["dims"]["avg_4dim"]
            life = project_effective_life(
                ld["balance"], ld["pandi"], ld["rate_pct"],
                mult, assumed_age, ld["rem"],
                use_seasoning=True, ramp_months=ramp,
            )
            life_total += life * ld["balance"]
        wtd_life = life_total / total_upb
        sensitivity.append(SeasoningSensitivityPoint(
            assumed_age_months=assumed_age,
            effective_life_months=round(wtd_life, 1),
            effective_life_years=round(wtd_life / 12, 2),
        ))

    # --- Loan details ---
    loan_details = []
    for ld in loan_data:
        d = ld["dims"]
        loan_details.append(LoanMultiplierDetail(
            loan_id=ld["loan_id"],
            credit_band=d["credit_band"],
            dim_credit=round(d["dim_credit"], 4),
            rate_delta_band=d["rate_delta_band"],
            dim_rate_delta=round(d["dim_rate_delta"], 4),
            ltv_band=d["ltv_band"],
            dim_ltv=round(d["dim_ltv"], 4),
            loan_size_band=d["loan_size_band"],
            dim_loan_size=round(d["dim_loan_size"], 4),
            avg_4dim=round(d["avg_4dim"], 4),
            balance=round(ld["balance"], 2),
            pandi=round(ld["pandi"], 2),
            rate_pct=round(ld["rate_pct"], 4),
            remaining_term=ld["rem"],
            loan_age=ld["age"],
        ))

    # --- Rate delta lookup table for frontend ---
    _, rate_delta_rates, _, _ = _get_apex2_tables()

    # --- Treasury rate curve scenarios (if provided) ---
    rate_curve_results = None
    if cfg.treasury_scenarios:
        rate_curve_results = []
        for scenario in cfg.treasury_scenarios:
            curve = [(p.month, p.rate) for p in scenario.points]
            life_total = 0.0
            for ld in loan_data:
                d = ld["dims"]
                life = project_effective_life_with_curve(
                    ld["balance"], ld["pandi"], ld["rate_pct"],
                    d["dim_credit"], d["dim_ltv"], d["dim_loan_size"],
                    curve, ld["age"], ld["rem"],
                    ramp_months=ramp,
                )
                life_total += life * ld["balance"]
            wtd_life = life_total / total_upb
            rate_curve_results.append(RateCurveScenarioResult(
                scenario_name=scenario.name,
                wtd_eff_life_months=round(wtd_life, 1),
                wtd_eff_life_years=round(wtd_life / 12, 2),
            ))

    return PrepaymentAnalysisResult(
        summary=summary,
        scenarios=scenarios,
        credit_bands=credit_bands,
        seasoning_sensitivity=sensitivity,
        loan_details=loan_details,
        rate_delta_rates=rate_delta_rates,
        rate_curve_results=rate_curve_results,
    )
