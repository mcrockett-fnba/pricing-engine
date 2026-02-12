"""Stub recovery model — formula-based, no trained artifact.

Provides recovery rates and timeline estimates by state (judicial vs non-judicial).
"""
from __future__ import annotations

# Recovery rate by bucket (fraction of defaulted balance recovered)
_RECOVERY_RATES = {
    1: 0.70,
    2: 0.60,
    3: 0.50,
    4: 0.40,
    5: 0.30,
}
_DEFAULT_RECOVERY = 0.50

# Foreclosure timelines in months — judicial states take longer
_JUDICIAL_STATES = {
    "CT", "DE", "FL", "HI", "IL", "IN", "IA", "KS", "KY", "LA",
    "ME", "MD", "MA", "NE", "NJ", "NM", "NY", "ND", "OH", "OK",
    "PA", "SC", "SD", "VT", "WI",
}
_JUDICIAL_MONTHS = 24
_NON_JUDICIAL_MONTHS = 12


def get_recovery_rate(bucket_id: int) -> float:
    """Return expected recovery rate (fraction 0-1) for a bucket."""
    return _RECOVERY_RATES.get(bucket_id, _DEFAULT_RECOVERY)


def get_recovery_amount(bucket_id: int, defaulted_balance: float) -> float:
    """Return estimated dollar recovery for a defaulted loan."""
    rate = get_recovery_rate(bucket_id)
    return defaulted_balance * rate


def get_foreclosure_timeline(state: str) -> int:
    """Return estimated months to complete foreclosure for a US state."""
    return _JUDICIAL_MONTHS if state.upper() in _JUDICIAL_STATES else _NON_JUDICIAL_MONTHS


def is_judicial_state(state: str) -> bool:
    """Return True if the state uses judicial foreclosure."""
    return state.upper() in _JUDICIAL_STATES
