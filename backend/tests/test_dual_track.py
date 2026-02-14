"""Dual-track valuation tests.

Covers Track A valuation, Track B provenance, dual-track calibration,
and API endpoint behavior.
"""
from fastapi.testclient import TestClient

from app.main import app
from app.models.loan import Loan
from app.models.package import Package
from app.models.simulation import SimulationConfig, TrackAConfig, ValuationTrack
from app.models.valuation import CalibrationMetrics, LoanValuationResult
from app.services.calibration_service import (
    calibrate_loan,
    calibrate_package,
    check_apex2_replication_gate,
)
from app.services.dual_track_service import valuate_loan, valuate_package
from app.services.track_a_valuation import track_a_loan_pv, valuate_loan_track_a, valuate_package_track_a

client = TestClient(app)


def _make_loan(**overrides) -> Loan:
    defaults = dict(
        loan_id="DT001",
        unpaid_balance=200_000.0,
        interest_rate=0.065,
        original_term=360,
        remaining_term=120,
        loan_age=240,
        credit_score=720,
        ltv=0.75,
    )
    defaults.update(overrides)
    return Loan(**defaults)


def _make_package(loans=None) -> Package:
    if loans is None:
        loans = [_make_loan()]
    return Package(
        package_id="PKG-DT01",
        name="Dual Track Test",
        loan_count=len(loans),
        total_upb=sum(l.unpaid_balance for l in loans),
        purchase_price=sum(l.unpaid_balance for l in loans) * 0.95,
        loans=loans,
    )


def _track_a_config() -> SimulationConfig:
    return SimulationConfig(
        n_simulations=0,
        include_stochastic=False,
        track=ValuationTrack.A,
        track_a_config=TrackAConfig(),
    )


def _track_b_config() -> SimulationConfig:
    return SimulationConfig(
        n_simulations=0,
        include_stochastic=False,
        track=ValuationTrack.B,
    )


def _both_config() -> SimulationConfig:
    return SimulationConfig(
        n_simulations=0,
        include_stochastic=False,
        track=ValuationTrack.both,
        track_a_config=TrackAConfig(),
    )


# ---------------------------------------------------------------------------
# Track A valuation (6 tests)
# ---------------------------------------------------------------------------


def test_track_a_loan_pv_positive():
    """Track A should produce a positive PV for a performing loan."""
    loan = _make_loan()
    cfg = TrackAConfig()
    pv, _ = track_a_loan_pv(loan, cfg)
    assert pv > 0, f"Track A PV should be positive, got {pv}"


def test_track_a_loan_returns_monthly_cash_flows():
    """Track A should produce month-by-month cash flows."""
    loan = _make_loan(remaining_term=60)
    cfg = TrackAConfig()
    _, cfs = track_a_loan_pv(loan, cfg)
    assert len(cfs) > 0, "Expected cash flows"
    assert cfs[0].month == 1
    # With APEX2 acceleration, effective life should be shorter than remaining term
    assert len(cfs) <= 60


def test_track_a_loan_provenance_tags():
    """Track A result should carry correct provenance metadata."""
    loan = _make_loan()
    config = _track_a_config()
    result = valuate_loan_track_a(loan, config)
    assert result.provenance is not None
    assert result.provenance.track == "A"
    assert result.provenance.prepayment_source == "APEX2_multiplier"
    assert result.provenance.discount_method == "target_yield"
    assert result.provenance.discount_rate_annual == 0.07


def test_track_a_higher_cdr_lowers_pv():
    """Higher CDR should produce lower PV (more credit losses)."""
    loan = _make_loan()
    low_cdr = TrackAConfig(annual_cdr=0.001)
    high_cdr = TrackAConfig(annual_cdr=0.05)
    pv_low, _ = track_a_loan_pv(loan, low_cdr)
    pv_high, _ = track_a_loan_pv(loan, high_cdr)
    assert pv_low > pv_high, (
        f"Higher CDR should lower PV: low={pv_low}, high={pv_high}"
    )


def test_track_a_package_roe_consistent():
    """Package ROE should be consistent with NPV and purchase price."""
    package = _make_package()
    config = _track_a_config()
    result = valuate_package_track_a(package, config)
    expected_roe = (result.expected_npv - result.purchase_price) / result.purchase_price
    assert abs(result.roe - expected_roe) < 1e-4, (
        f"ROE mismatch: result={result.roe}, computed={expected_roe}"
    )


def test_track_a_deterministic_no_mc():
    """Track A should produce empty MC distributions (deterministic only)."""
    loan = _make_loan()
    config = _track_a_config()
    result = valuate_loan_track_a(loan, config)
    assert result.pv_distribution == []
    assert result.pv_percentiles == {}


# ---------------------------------------------------------------------------
# Track B provenance (3 tests)
# ---------------------------------------------------------------------------


def test_track_b_has_provenance():
    """Track B result should carry provenance metadata."""
    loan = _make_loan()
    config = _track_b_config()
    result = valuate_loan(loan, config)
    assert result.provenance is not None
    assert result.provenance.track == "B"
    assert result.provenance.prepayment_source == "KM_survival_hazard"


def test_track_b_backward_compatible():
    """Default SimulationConfig (track=B) should produce identical results
    to the original simulate_loan."""
    from app.simulation.engine import simulate_loan

    loan = _make_loan()
    config = SimulationConfig(n_simulations=0, include_stochastic=False)
    # Default track is B
    assert config.track == ValuationTrack.B

    original = simulate_loan(loan, config)
    via_dual = valuate_loan(loan, config)

    assert original.expected_pv == via_dual.expected_pv
    assert original.pv_by_scenario == via_dual.pv_by_scenario


def test_track_b_results_match_direct_engine():
    """Package via dual_track (track=B) should match direct simulation_service."""
    from app.services.simulation_service import run_valuation

    package = _make_package()
    config = _track_b_config()
    direct = run_valuation(package, config)
    via_dual = valuate_package(package, config)

    assert direct.expected_npv == via_dual.expected_npv
    assert direct.roe == via_dual.roe


# ---------------------------------------------------------------------------
# Dual-track / calibration (8 tests)
# ---------------------------------------------------------------------------


def test_both_tracks_returns_calibration_summary():
    """track=both should produce calibration_summary on package result."""
    package = _make_package()
    config = _both_config()
    result = valuate_package(package, config)
    assert result.calibration_summary is not None
    assert result.calibration_summary.track_a_pv is not None
    assert result.calibration_summary.track_b_pv is not None
    assert result.tolerance_gate_passed is not None


def test_both_tracks_loan_level_calibration():
    """track=both should attach calibration to each loan result."""
    package = _make_package()
    config = _both_config()
    result = valuate_package(package, config)
    for lr in result.loan_results:
        assert lr.calibration is not None
        assert lr.calibration.track_a_pv is not None
        assert lr.calibration.track_b_pv is not None


def test_calibration_metrics_arithmetic():
    """Calibration metrics should be arithmetically correct."""
    a = LoanValuationResult(
        loan_id="A", bucket_id=1, expected_pv=100_000.0,
        pv_by_scenario={}, pv_distribution=[], pv_percentiles={},
        monthly_cash_flows=[], model_status={},
    )
    b = LoanValuationResult(
        loan_id="B", bucket_id=1, expected_pv=102_000.0,
        pv_by_scenario={}, pv_distribution=[], pv_percentiles={},
        monthly_cash_flows=[], model_status={},
    )
    cal = calibrate_loan(a, b)
    assert cal.absolute_error == 2_000.0
    assert abs(cal.relative_error_pct - 2.0) < 0.01


def test_calibrate_loan_within_tolerance():
    """Loan within 2.5% tolerance should pass."""
    a = LoanValuationResult(
        loan_id="A", bucket_id=1, expected_pv=100_000.0,
        pv_by_scenario={}, pv_distribution=[], pv_percentiles={},
        monthly_cash_flows=[], model_status={},
    )
    b = LoanValuationResult(
        loan_id="B", bucket_id=1, expected_pv=101_000.0,
        pv_by_scenario={}, pv_distribution=[], pv_percentiles={},
        monthly_cash_flows=[], model_status={},
    )
    cal = calibrate_loan(a, b, tolerance_pct=2.5)
    assert cal.within_tolerance is True


def test_calibrate_loan_outside_tolerance():
    """Loan outside 2.5% tolerance should fail."""
    a = LoanValuationResult(
        loan_id="A", bucket_id=1, expected_pv=100_000.0,
        pv_by_scenario={}, pv_distribution=[], pv_percentiles={},
        monthly_cash_flows=[], model_status={},
    )
    b = LoanValuationResult(
        loan_id="B", bucket_id=1, expected_pv=110_000.0,
        pv_by_scenario={}, pv_distribution=[], pv_percentiles={},
        monthly_cash_flows=[], model_status={},
    )
    cal = calibrate_loan(a, b, tolerance_pct=2.5)
    assert cal.within_tolerance is False


def test_tolerance_gate_passed_flag():
    """tolerance_gate_passed on package should reflect calibration outcome."""
    package = _make_package()
    config = _both_config()
    result = valuate_package(package, config)
    # Whether it passes depends on actual model divergence, but the flag should exist
    assert isinstance(result.tolerance_gate_passed, bool)
    assert result.calibration_summary.within_tolerance == result.tolerance_gate_passed


def test_roe_tolerance_gate_50bps():
    """ROE tolerance gate should use basis point comparison."""
    from app.models.valuation import PackageValuationResult
    from app.services.calibration_service import calibrate_package as cal_pkg
    from datetime import datetime, timezone

    base_kwargs = dict(
        package_id="P", package_name="P", loan_count=1, total_upb=100_000,
        purchase_price=95_000, npv_by_scenario={}, npv_distribution=[],
        npv_percentiles={}, loan_results=[], simulation_config=SimulationConfig(),
        model_manifest={}, computed_at=datetime.now(timezone.utc),
        roe_distribution=[], roe_percentiles={}, roe_by_scenario={},
    )

    # ROE diff = 0.01 = 100 bps → should fail 50 bps gate
    a = PackageValuationResult(expected_npv=100_000, roe=0.05, roe_annualized=0.05, **base_kwargs)
    b = PackageValuationResult(expected_npv=100_000, roe=0.06, roe_annualized=0.06, **base_kwargs)
    cal = cal_pkg(a, b, tolerance_pct=100.0, roe_tolerance_bps=50)
    assert cal.within_tolerance is False
    assert cal.roe_diff_bps == 100.0

    # ROE diff = 0.002 = 20 bps → should pass 50 bps gate
    c = PackageValuationResult(expected_npv=100_000, roe=0.050, roe_annualized=0.050, **base_kwargs)
    d = PackageValuationResult(expected_npv=100_000, roe=0.052, roe_annualized=0.052, **base_kwargs)
    cal2 = cal_pkg(c, d, tolerance_pct=100.0, roe_tolerance_bps=50)
    assert cal2.within_tolerance is True
    assert cal2.roe_diff_bps == 20.0


def test_apex2_replication_gate():
    """APEX2 replication gate should compare Track A to an APEX2 reference."""
    cal = check_apex2_replication_gate(
        track_a_pv=100_000.0,
        apex2_replicated_pv=100_500.0,
        threshold_pct=1.5,
    )
    assert cal.within_tolerance is True
    assert abs(cal.relative_error_pct - 0.4975) < 0.01

    cal2 = check_apex2_replication_gate(
        track_a_pv=100_000.0,
        apex2_replicated_pv=105_000.0,
        threshold_pct=1.5,
    )
    assert cal2.within_tolerance is False


# ---------------------------------------------------------------------------
# API endpoint (3 tests)
# ---------------------------------------------------------------------------

_SAMPLE_LOAN = {
    "loan_id": "L001",
    "unpaid_balance": 200_000.0,
    "interest_rate": 0.065,
    "original_term": 360,
    "remaining_term": 120,
    "loan_age": 240,
    "credit_score": 720,
    "ltv": 0.75,
}

_SAMPLE_PACKAGE = {
    "package_id": "PKG-001",
    "name": "Test Package",
    "loan_count": 1,
    "total_upb": 200_000.0,
    "purchase_price": 190_000.0,
    "loans": [_SAMPLE_LOAN],
}


def test_valuation_track_a_returns_200():
    response = client.post("/api/valuations/run", json={
        "package": _SAMPLE_PACKAGE,
        "config": {
            "n_simulations": 0,
            "include_stochastic": False,
            "track": "A",
            "track_a_config": {"target_yield": 0.07},
        },
    })
    assert response.status_code == 200
    data = response.json()
    assert data["provenance"]["track"] == "A"


def test_valuation_track_both_returns_200():
    response = client.post("/api/valuations/run", json={
        "package": _SAMPLE_PACKAGE,
        "config": {
            "n_simulations": 0,
            "include_stochastic": False,
            "track": "both",
            "track_a_config": {"target_yield": 0.07},
        },
    })
    assert response.status_code == 200
    data = response.json()
    assert data["calibration_summary"] is not None
    assert data["tolerance_gate_passed"] is not None


def test_valuation_default_track_backward_compatible():
    """Default request (no track specified) should still work as Track B."""
    response = client.post("/api/valuations/run", json={
        "package": _SAMPLE_PACKAGE,
        "config": {"n_simulations": 0, "include_stochastic": False},
    })
    assert response.status_code == 200
    data = response.json()
    assert data["expected_npv"] is not None
    assert data["loan_results"][0]["expected_pv"] is not None
