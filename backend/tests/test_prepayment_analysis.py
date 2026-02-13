"""Tests for the APEX2 prepayment analysis service and endpoint."""
import math

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.package import Package
from app.models.prepayment import PrepaymentConfig
from app.services.prepayment_analysis import (
    apex2_amortize,
    compute_apex2_multiplier,
    compute_pandi,
    get_credit_band,
    project_effective_life,
    run_prepayment_analysis,
)

client = TestClient(app)

_SAMPLE_LOAN = {
    "loan_id": "L001",
    "unpaid_balance": 200_000.0,
    "interest_rate": 0.065,
    "original_term": 360,
    "remaining_term": 280,
    "loan_age": 80,
    "credit_score": 660,
    "ltv": 0.85,
}

_THREE_LOAN_PACKAGE = {
    "package_id": "PKG-TEST",
    "name": "Test Package",
    "loan_count": 3,
    "total_upb": 600_000.0,
    "loans": [
        {
            "loan_id": "L001",
            "unpaid_balance": 250_000.0,
            "interest_rate": 0.072,
            "original_term": 360,
            "remaining_term": 280,
            "loan_age": 80,
            "credit_score": 660,
            "ltv": 0.85,
        },
        {
            "loan_id": "L002",
            "unpaid_balance": 200_000.0,
            "interest_rate": 0.068,
            "original_term": 360,
            "remaining_term": 300,
            "loan_age": 60,
            "credit_score": 720,
            "ltv": 0.78,
        },
        {
            "loan_id": "L003",
            "unpaid_balance": 150_000.0,
            "interest_rate": 0.082,
            "original_term": 240,
            "remaining_term": 180,
            "loan_age": 60,
            "credit_score": 590,
            "ltv": 0.95,
        },
    ],
}


def test_compute_pandi():
    """Standard amortization P&I should match known values."""
    # $200,000 at 6.5% for 360 months → ~$1,264.14
    pandi = compute_pandi(200_000, 6.5, 360)
    assert 1260 < pandi < 1270


def test_compute_pandi_zero_rate():
    """Zero rate should return simple division."""
    pandi = compute_pandi(120_000, 0.0, 360)
    assert abs(pandi - 120_000 / 360) < 0.01


def test_compute_apex2_multiplier_bands():
    """Verify band assignment and multiplier retrieval."""
    dims = compute_apex2_multiplier(660, 7.2, 85, 240_000, 4.5)
    assert dims["credit_band"] == "651-675"
    assert dims["dim_credit"] == 2.4668
    assert dims["rate_delta_band"] == "2 to 2.99%"
    assert dims["ltv_band"] == "85% - 89.99%"
    assert dims["loan_size_band"] == "$200,000 - $249,999"
    # avg_4dim should be mean of 4 dimensions
    expected_avg = (dims["dim_credit"] + dims["dim_rate_delta"] + dims["dim_ltv"] + dims["dim_loan_size"]) / 4
    assert abs(dims["avg_4dim"] - expected_avg) < 0.0001


def test_apex2_amortize_matches_known():
    """NPER calculation should match Excel NPER-like result."""
    # $200,000 at 6.5%, monthly payment of $1264.14 → should be 360 months
    nper = apex2_amortize(200_000, 1264.14, 6.5)
    assert nper is not None
    assert 358 <= nper <= 362  # rounding tolerance


def test_apex2_amortize_with_higher_payment():
    """Higher payment → fewer months."""
    nper_base = apex2_amortize(200_000, 1264.14, 6.5)
    nper_fast = apex2_amortize(200_000, 2500, 6.5)
    assert nper_fast is not None
    assert nper_fast < nper_base


def test_project_effective_life_flat_vs_seasoned():
    """Seasoning ramp should make effective life longer for new loans."""
    pandi = compute_pandi(200_000, 7.0, 280)
    # Flat: no seasoning effect
    life_flat = project_effective_life(200_000, pandi, 7.0, 2.5, 0, 280, use_seasoning=False)
    # Seasoned starting from age 0: ramp slows prepay initially
    life_seasoned = project_effective_life(200_000, pandi, 7.0, 2.5, 0, 280, use_seasoning=True)
    assert life_seasoned > life_flat


def test_run_analysis_structure():
    """Full integration: 3-loan package should return all fields."""
    pkg = Package(**_THREE_LOAN_PACKAGE)
    result = run_prepayment_analysis(pkg)

    assert result.summary.loan_count == 3
    assert result.summary.total_upb > 0
    assert result.summary.wtd_avg_rate > 0
    assert result.summary.wtd_avg_credit > 0
    # 6 scenarios: 2 sources × 3 methods
    assert len(result.scenarios) == 6
    assert all(s.monthly_months > 0 for s in result.scenarios)
    assert all(s.monthly_years > 0 for s in result.scenarios)
    assert len(result.loan_details) == 3
    assert len(result.seasoning_sensitivity) > 0


def test_run_analysis_credit_bands_populated():
    """Credit bands should group the 3 test loans correctly."""
    pkg = Package(**_THREE_LOAN_PACKAGE)
    result = run_prepayment_analysis(pkg)

    assert len(result.credit_bands) >= 2  # 590, 660, 720 span multiple bands
    total_loans = sum(b.loan_count for b in result.credit_bands)
    assert total_loans == 3


def test_run_analysis_seasoning_sensitivity_decreasing():
    """Older assumed age should produce shorter or equal effective life."""
    pkg = Package(**_THREE_LOAN_PACKAGE)
    result = run_prepayment_analysis(pkg)

    lives = [p.effective_life_months for p in result.seasoning_sensitivity]
    # Each point should be <= the previous (seasoning makes prepay faster)
    for i in range(1, len(lives)):
        assert lives[i] <= lives[i - 1] + 0.1  # small tolerance for rounding


def test_missing_credit_score_defaults():
    """Loan with no credit_score should default to 700."""
    loan_no_credit = {**_SAMPLE_LOAN, "credit_score": None}
    pkg = Package(
        package_id="PKG-DEF",
        name="Default Test",
        loan_count=1,
        total_upb=200_000.0,
        loans=[loan_no_credit],
    )
    result = run_prepayment_analysis(pkg)
    # Should have picked up credit band for 700
    detail = result.loan_details[0]
    assert detail.credit_band == "676-700"


def test_endpoint_returns_200():
    """POST to /api/prepayment/analyze with valid package."""
    response = client.post("/api/prepayment/analyze", json={
        "package": _THREE_LOAN_PACKAGE,
    })
    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
    assert "scenarios" in data
    assert "credit_bands" in data
    assert "seasoning_sensitivity" in data
    assert "loan_details" in data
    assert data["summary"]["loan_count"] == 3
