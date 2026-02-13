"""Tests for the stub prepayment model — CPR/SMM, seasoning, rate incentive."""
import math

from app.ml.stub_prepayment import (
    cpr_to_smm,
    get_prepay_hazard,
    rate_incentive_factor,
    seasoning_multiplier,
)


# --- CPR ↔ SMM conversion ---


def test_smm_zero_cpr():
    assert cpr_to_smm(0.0) == 0.0


def test_smm_roundtrip():
    """SMM back to CPR: CPR = 1 - (1 - SMM)^12."""
    cpr = 0.10
    smm = cpr_to_smm(cpr)
    recovered_cpr = 1.0 - (1.0 - smm) ** 12
    assert abs(recovered_cpr - cpr) < 1e-10


def test_smm_known_value():
    """10% CPR should give ~0.87% SMM."""
    smm = cpr_to_smm(0.10)
    assert abs(smm - 0.00874) < 0.001


def test_smm_clamped_above_one():
    """CPR > 1.0 should be clamped."""
    smm = cpr_to_smm(1.5)
    assert smm == 1.0


# --- Seasoning ramp ---


def test_seasoning_at_zero():
    assert seasoning_multiplier(0) == 0.0


def test_seasoning_at_15_months():
    assert abs(seasoning_multiplier(15) - 0.5) < 1e-10


def test_seasoning_at_30_months():
    assert abs(seasoning_multiplier(30) - 1.0) < 1e-10


def test_seasoning_capped_above_30():
    assert seasoning_multiplier(60) == 1.0
    assert seasoning_multiplier(120) == 1.0


# --- Rate incentive factor ---


def test_rate_incentive_out_of_money():
    """Loan rate below market → 0.5x."""
    factor = rate_incentive_factor(0.04, market_rate=0.065)
    assert factor == 0.5


def test_rate_incentive_at_par():
    """Loan rate ≈ market → 1.0x."""
    factor = rate_incentive_factor(0.065, market_rate=0.065)
    assert factor == 1.0


def test_rate_incentive_in_the_money():
    """Loan rate well above market → up to 4.0x."""
    factor = rate_incentive_factor(0.09, market_rate=0.065)
    assert factor >= 3.0
    assert factor <= 4.0


# --- get_prepay_hazard ---


def test_bucket_ordering():
    """Prime loans should prepay faster than sub-prime."""
    age, rate = 60, 0.065
    h1 = get_prepay_hazard(1, age, rate)
    h4 = get_prepay_hazard(4, age, rate)
    h5 = get_prepay_hazard(5, age, rate)
    assert h1 > h4 > h5


def test_seasoning_effect():
    """New loans should have lower prepay hazard than seasoned ones."""
    h_new = get_prepay_hazard(3, 5, 0.065)
    h_seasoned = get_prepay_hazard(3, 60, 0.065)
    assert h_seasoned > h_new


def test_rate_effect():
    """Higher loan rate → higher prepay hazard (refi incentive)."""
    h_low = get_prepay_hazard(3, 60, 0.04)
    h_high = get_prepay_hazard(3, 60, 0.10)
    assert h_high > h_low


def test_positive_for_all_buckets():
    """All buckets should produce positive SMM for seasoned loans."""
    for bid in range(1, 6):
        h = get_prepay_hazard(bid, 60, 0.065)
        assert h > 0.0


def test_capped_below_one():
    """Even extreme inputs should not exceed SMM = 1.0."""
    h = get_prepay_hazard(1, 120, 0.20, market_rate=0.03)
    assert h < 1.0
