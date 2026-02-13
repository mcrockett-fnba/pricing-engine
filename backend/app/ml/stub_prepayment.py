"""Stub prepayment model — formula-based competing-risk prepayment hazard.

Provides month-by-month prepayment probability (SMM) by bucket, loan age,
and rate incentive. Base CPR calibrated to ~8-10 year effective life on
typical non-prime loan tapes.
"""
from __future__ import annotations

# Base annual CPR by bucket (higher = more likely to prepay)
_BASE_CPR: dict[int, float] = {
    1: 0.12,   # Prime — best refi access
    2: 0.10,   # Near-Prime — good refi access
    3: 0.07,   # Non-Prime — limited options
    4: 0.04,   # Sub-Prime — few options
    5: 0.02,   # Deep Sub-Prime — essentially trapped
}
_DEFAULT_CPR = 0.07

_MAX_CPR = 0.60  # Hard cap on annual CPR
_SEASONING_RAMP_MONTHS = 30  # PSA-style linear ramp


def cpr_to_smm(cpr: float) -> float:
    """Convert annual CPR to single monthly mortality (SMM).

    SMM = 1 - (1 - CPR)^(1/12)
    """
    cpr = max(0.0, min(cpr, 1.0))
    return 1.0 - (1.0 - cpr) ** (1.0 / 12.0)


def seasoning_multiplier(loan_age: int) -> float:
    """PSA-style seasoning ramp: linear 0→1 over first 30 months."""
    if loan_age <= 0:
        return 0.0
    return min(loan_age / _SEASONING_RAMP_MONTHS, 1.0)


def rate_incentive_factor(loan_rate: float, market_rate: float = 0.065) -> float:
    """Rate incentive multiplier for prepayment.

    - loan_rate < market_rate → 0.5x (some moves/sales still happen)
    - loan_rate ≈ market_rate → 1.0x
    - loan_rate > market_rate + 2% → up to 4.0x (strong refi incentive)
    """
    spread = loan_rate - market_rate
    if spread <= -0.01:
        return 0.5
    if spread <= 0.01:
        return 1.0
    # Linear ramp from 1.0 at +1% to 4.0 at +2%
    factor = 1.0 + 3.0 * min((spread - 0.01) / 0.01, 1.0)
    return factor


def get_prepay_hazard(
    bucket_id: int,
    loan_age: int,
    loan_rate: float,
    market_rate: float = 0.065,
) -> float:
    """Return monthly prepayment hazard (SMM) for a loan.

    Combines base CPR, seasoning ramp, and rate incentive, then converts
    to monthly SMM. Result is capped to prevent unrealistic values.
    """
    base_cpr = _BASE_CPR.get(bucket_id, _DEFAULT_CPR)
    adjusted_cpr = base_cpr * seasoning_multiplier(loan_age) * rate_incentive_factor(loan_rate, market_rate)
    capped_cpr = min(adjusted_cpr, _MAX_CPR)
    return cpr_to_smm(capped_cpr)
