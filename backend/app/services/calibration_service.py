"""Calibration service — compares Track A and Track B valuation results.

Pure arithmetic. No external dependencies beyond model types.
"""
from __future__ import annotations

from app.models.valuation import (
    CalibrationMetrics,
    LoanValuationResult,
    PackageValuationResult,
)

TRACK_B_VS_TRACK_A_THRESHOLD_PCT = 2.5
ROE_TOLERANCE_BPS = 50.0
TRACK_A_VS_APEX2_THRESHOLD_PCT = 1.5


def calibrate_loan(
    track_a_result: LoanValuationResult,
    track_b_result: LoanValuationResult,
    tolerance_pct: float = TRACK_B_VS_TRACK_A_THRESHOLD_PCT,
) -> CalibrationMetrics:
    """Compare loan-level PVs between Track A and Track B."""
    a_pv = track_a_result.expected_pv
    b_pv = track_b_result.expected_pv

    abs_err = abs(b_pv - a_pv)
    rel_err = (abs_err / abs(a_pv) * 100.0) if a_pv != 0 else 0.0

    return CalibrationMetrics(
        track_a_pv=round(a_pv, 2),
        track_b_pv=round(b_pv, 2),
        absolute_error=round(abs_err, 2),
        relative_error_pct=round(rel_err, 4),
        within_tolerance=rel_err <= tolerance_pct,
        tolerance_threshold_pct=tolerance_pct,
    )


def calibrate_package(
    track_a_result: PackageValuationResult,
    track_b_result: PackageValuationResult,
    tolerance_pct: float = TRACK_B_VS_TRACK_A_THRESHOLD_PCT,
    roe_tolerance_bps: float = ROE_TOLERANCE_BPS,
) -> CalibrationMetrics:
    """Compare package-level PVs and ROEs between Track A and Track B."""
    a_pv = track_a_result.expected_npv
    b_pv = track_b_result.expected_npv

    abs_err = abs(b_pv - a_pv)
    rel_err = (abs_err / abs(a_pv) * 100.0) if a_pv != 0 else 0.0

    roe_a = track_a_result.roe
    roe_b = track_b_result.roe
    roe_diff = abs(roe_b - roe_a) * 10_000  # convert to bps

    pv_within = rel_err <= tolerance_pct
    roe_within = roe_diff <= roe_tolerance_bps
    within = pv_within and roe_within

    return CalibrationMetrics(
        track_a_pv=round(a_pv, 2),
        track_b_pv=round(b_pv, 2),
        absolute_error=round(abs_err, 2),
        relative_error_pct=round(rel_err, 4),
        roe_a=round(roe_a, 6),
        roe_b=round(roe_b, 6),
        roe_diff_bps=round(roe_diff, 2),
        within_tolerance=within,
        tolerance_threshold_pct=tolerance_pct,
    )


def check_apex2_replication_gate(
    track_a_pv: float,
    apex2_replicated_pv: float,
    threshold_pct: float = TRACK_A_VS_APEX2_THRESHOLD_PCT,
) -> CalibrationMetrics:
    """Check whether Track A replicates APEX2 within threshold."""
    abs_err = abs(track_a_pv - apex2_replicated_pv)
    rel_err = (abs_err / abs(apex2_replicated_pv) * 100.0) if apex2_replicated_pv != 0 else 0.0

    return CalibrationMetrics(
        track_a_pv=round(track_a_pv, 2),
        track_b_pv=round(apex2_replicated_pv, 2),
        absolute_error=round(abs_err, 2),
        relative_error_pct=round(rel_err, 4),
        within_tolerance=rel_err <= threshold_pct,
        tolerance_threshold_pct=threshold_pct,
    )
