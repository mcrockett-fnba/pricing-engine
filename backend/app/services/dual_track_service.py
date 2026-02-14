"""Dual-track valuation orchestrator.

Routes to Track A, Track B, or both based on SimulationConfig.track.
When track=both, runs both and attaches calibration metrics to the
Track B result (primary return, since it has MC distributions).
"""
from __future__ import annotations

from app.models.loan import Loan
from app.models.package import Package
from app.models.simulation import PrepayModel, SimulationConfig, ValuationTrack
from app.models.valuation import (
    LoanValuationResult,
    ModelProvenance,
    PackageValuationResult,
)
from app.ml.model_loader import ModelRegistry
from app.services.calibration_service import calibrate_loan, calibrate_package
from app.services.simulation_service import run_valuation as run_track_b_valuation
from app.services.track_a_valuation import valuate_loan_track_a, valuate_package_track_a
from app.simulation.engine import simulate_loan as run_track_b_loan

_TRACK_B_VERSION = "1.0.0"


def _get_track_b_provenance(config: SimulationConfig | None = None) -> ModelProvenance:
    registry = ModelRegistry.get()
    if config and config.prepay_model == PrepayModel.km_only:
        cdr_pct = config.annual_cdr * 100
        prepay_source = f"KM_only (CDR={cdr_pct:.2f}%)"
        credit_model = f"flat_CDR_{cdr_pct:.2f}pct"
    else:
        prepay_source = "KM_survival_hazard"
        credit_model = "KM_state_transitions"
    return ModelProvenance(
        track="B",
        track_b_version=_TRACK_B_VERSION,
        prepayment_source=prepay_source,
        credit_model=credit_model,
        discount_method="cost_of_capital",
        discount_rate_annual=0.08,
    )


def valuate_loan(loan: Loan, config: SimulationConfig) -> LoanValuationResult:
    """Dispatch loan valuation to the appropriate track."""
    track = config.track

    if track == ValuationTrack.A:
        return valuate_loan_track_a(loan, config)

    if track == ValuationTrack.B:
        result = run_track_b_loan(loan, config)
        result.provenance = _get_track_b_provenance(config)
        return result

    # track == both: run both, calibrate, return Track B with calibration
    track_a = valuate_loan_track_a(loan, config)
    track_b = run_track_b_loan(loan, config)
    track_b.provenance = _get_track_b_provenance(config)
    track_b.calibration = calibrate_loan(track_a, track_b)
    return track_b


def valuate_package(package: Package, config: SimulationConfig) -> PackageValuationResult:
    """Dispatch package valuation to the appropriate track."""
    track = config.track

    if track == ValuationTrack.A:
        return valuate_package_track_a(package, config)

    if track == ValuationTrack.B:
        result = run_track_b_valuation(package, config)
        result.provenance = _get_track_b_provenance(config)
        return result

    # track == both: run both, calibrate, return Track B with calibration
    track_a = valuate_package_track_a(package, config)
    track_b = run_track_b_valuation(package, config)
    track_b.provenance = _get_track_b_provenance(config)

    cal = calibrate_package(track_a, track_b)
    track_b.calibration_summary = cal
    track_b.tolerance_gate_passed = cal.within_tolerance

    # Attach per-loan calibration if both have same loan count and ordering
    if len(track_a.loan_results) == len(track_b.loan_results):
        for lr_a, lr_b in zip(track_a.loan_results, track_b.loan_results):
            lr_b.calibration = calibrate_loan(lr_a, lr_b)

    return track_b
