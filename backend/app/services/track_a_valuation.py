"""Track A (APEX2-compatible) valuation service.

Deterministic valuation using APEX2 prepay multipliers + flat CDR credit model,
discounted at target ROE yield. No Monte Carlo — single deterministic path.

Promoted from _calibrated_cf_pv() in scripts/pricing_validation_report.py.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.models.loan import Loan
from app.models.package import Package
from app.models.simulation import SimulationConfig, TrackAConfig
from app.models.valuation import (
    CalibrationMetrics,
    LoanValuationResult,
    ModelProvenance,
    MonthlyCashFlow,
    PackageValuationResult,
)
from app.ml.bucket_assigner import assign_bucket
from app.services.prepayment_analysis import (
    compute_apex2_multiplier,
    compute_pandi,
)

_TRACK_A_VERSION = "1.0.0"
_SERVICING_ANNUAL = 0.0025  # 25 bps


def _get_track_a_provenance(config: TrackAConfig) -> ModelProvenance:
    return ModelProvenance(
        track="A",
        track_a_version=_TRACK_A_VERSION,
        prepayment_source="APEX2_multiplier",
        credit_model=f"flat_CDR_{config.annual_cdr}",
        discount_method="target_yield",
        discount_rate_annual=config.target_yield,
    )


def track_a_loan_pv(
    loan: Loan,
    track_a_config: TrackAConfig,
) -> tuple[float, list[MonthlyCashFlow]]:
    """Core Track A loop: APEX2 prepay schedule + flat CDR + target yield discount.

    Returns (total_pv, list_of_monthly_cash_flows).
    """
    cfg = track_a_config
    r_yield = cfg.target_yield / 12.0
    r_loan = loan.interest_rate / 12.0
    balance = loan.unpaid_balance
    n_months = loan.remaining_term

    # Scheduled P&I
    rate_pct = loan.interest_rate * 100
    pandi = compute_pandi(balance, rate_pct, n_months)

    # APEX2 multiplier
    ltv_pct = (loan.ltv or 0.80) * 100
    credit = float(loan.credit_score or 700)
    dims = compute_apex2_multiplier(credit, rate_pct, ltv_pct, balance, cfg.treasury_10y)
    prepay_mult = dims["avg_4dim"]

    # Effective (accelerated) payment
    eff_pmt = pandi * max(prepay_mult, 1.0)

    # Monthly default probability from annual CDR
    monthly_default = 1.0 - (1.0 - cfg.annual_cdr) ** (1.0 / 12.0)
    net_lgd = 1.0 - cfg.recovery_rate
    servicing_monthly = _SERVICING_ANNUAL / 12.0

    bucket_id = assign_bucket(loan.model_dump())

    cumul_surv = 1.0
    total_pv = 0.0
    cash_flows: list[MonthlyCashFlow] = []

    for month_num in range(1, n_months + 1):
        if balance <= 0.01:
            break

        surv_entering = cumul_surv

        # Credit defaults reduce the performing pool
        cumul_surv *= (1.0 - monthly_default)

        # Payment capped at balance + interest
        interest = balance * r_loan
        payment = min(eff_pmt, balance + interest)
        expected_pmt = payment * cumul_surv

        # Credit loss: defaulted portion x net LGD
        net_credit_loss = monthly_default * net_lgd * balance * surv_entering

        # Servicing on surviving balance
        serv = balance * servicing_monthly * cumul_surv

        net_cf = expected_pmt - net_credit_loss - serv

        # Discount at target yield
        df = 1.0 / (1.0 + r_yield) ** month_num
        pv = net_cf * df
        total_pv += pv

        cash_flows.append(MonthlyCashFlow(
            month=month_num,
            scheduled_payment=round(payment, 2),
            survival_probability=round(cumul_surv, 6),
            expected_payment=round(expected_pmt, 2),
            deq_probability=0.0,
            default_probability=round(monthly_default, 6),
            expected_loss=round(net_credit_loss, 2),
            expected_recovery=0.0,
            prepay_probability=0.0,
            expected_prepayment=0.0,
            servicing_cost=round(serv, 2),
            net_cash_flow=round(net_cf, 2),
            discount_factor=round(df, 6),
            present_value=round(pv, 2),
        ))

        # Amortize: accelerated principal + default exits
        principal = min(payment - interest, balance)
        default_red = monthly_default * balance * surv_entering
        balance = max(balance - principal - default_red, 0.0)

    return total_pv, cash_flows


def valuate_loan_track_a(
    loan: Loan,
    config: SimulationConfig,
) -> LoanValuationResult:
    """Track A valuation for a single loan. Deterministic only — no MC."""
    track_a_cfg = config.track_a_config or TrackAConfig()
    total_pv, cash_flows = track_a_loan_pv(loan, track_a_cfg)
    bucket_id = assign_bucket(loan.model_dump())

    return LoanValuationResult(
        loan_id=loan.loan_id,
        bucket_id=bucket_id,
        expected_pv=round(total_pv, 2),
        pv_by_scenario={"baseline": round(total_pv, 2)},
        pv_distribution=[],
        pv_percentiles={},
        monthly_cash_flows=cash_flows,
        model_status={"track": "A"},
        provenance=_get_track_a_provenance(track_a_cfg),
    )


def valuate_package_track_a(
    package: Package,
    config: SimulationConfig,
) -> PackageValuationResult:
    """Track A valuation for a full package. Sums loan PVs, computes ROE."""
    track_a_cfg = config.track_a_config or TrackAConfig()
    loan_results = [valuate_loan_track_a(loan, config) for loan in package.loans]

    expected_npv = sum(lr.expected_pv for lr in loan_results)
    purchase_price = package.purchase_price or package.total_upb

    roe = (expected_npv - purchase_price) / purchase_price if purchase_price else 0.0

    avg_term_months = (
        sum(loan.remaining_term for loan in package.loans) / len(package.loans)
        if package.loans else 360
    )
    avg_term_years = avg_term_months / 12.0
    if avg_term_years > 0 and roe > -1.0:
        roe_annualized = (1.0 + roe) ** (1.0 / avg_term_years) - 1.0
    else:
        roe_annualized = roe

    provenance = _get_track_a_provenance(track_a_cfg)

    return PackageValuationResult(
        package_id=package.package_id,
        package_name=package.name,
        loan_count=len(loan_results),
        total_upb=package.total_upb,
        purchase_price=purchase_price,
        expected_npv=round(expected_npv, 2),
        roe=round(roe, 6),
        roe_annualized=round(roe_annualized, 6),
        roe_by_scenario={"baseline": round(roe, 6)},
        roe_distribution=[],
        roe_percentiles={},
        npv_by_scenario={"baseline": round(expected_npv, 2)},
        npv_distribution=[],
        npv_percentiles={},
        loan_results=loan_results,
        simulation_config=config,
        model_manifest={"track": "A", "version": _TRACK_A_VERSION},
        computed_at=datetime.now(timezone.utc),
        provenance=provenance,
    )
