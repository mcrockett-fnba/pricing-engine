"""Stub default model — formula-based, no trained artifact.

Provides default probability by DPD severity and loss severity by bucket.
"""
from __future__ import annotations

# Default probability by days-past-due severity tier
_DEFAULT_PROB_BY_DPD = {
    "current": 0.0,
    "30dpd": 0.05,
    "60dpd": 0.15,
    "90dpd": 0.35,
    "120dpd": 0.55,
    "150dpd": 0.70,
    "180dpd": 0.85,
}

# Loss severity (loss-given-default) by bucket
_LOSS_SEVERITY = {
    1: 0.20,
    2: 0.25,
    3: 0.35,
    4: 0.45,
    5: 0.55,
}
_DEFAULT_SEVERITY = 0.35


def get_default_probability(dpd_severity: str) -> float:
    """Return probability of default for a given DPD severity tier.

    Valid tiers: current, 30dpd, 60dpd, 90dpd, 120dpd, 150dpd, 180dpd.
    """
    return _DEFAULT_PROB_BY_DPD.get(dpd_severity.lower(), 0.0)


def get_loss_severity(bucket_id: int = 3) -> float:
    """Return loss-given-default as a fraction (0-1) for a bucket."""
    return _LOSS_SEVERITY.get(bucket_id, _DEFAULT_SEVERITY)
