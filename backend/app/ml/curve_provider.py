"""Curve provider — given a bucket_id, returns survival curve probabilities.

3-tier fallback:
1. From loaded parquet data (ModelRegistry.survival_curves)
2. Average curve fallback if bucket_id is missing from loaded data
3. Generated stub curve if no parquet loaded at all
"""
from __future__ import annotations

import math
import logging

from app.ml.model_loader import ModelRegistry

logger = logging.getLogger(__name__)

# Annual hazard rates per bucket (same as generate_stub_models.py)
_HAZARD_RATES = {1: 0.005, 2: 0.010, 3: 0.020, 4: 0.040, 5: 0.070}
_DEFAULT_HAZARD = 0.020  # Non-Prime as middle-ground default


def get_survival_curve(bucket_id: int, n_months: int = 360) -> list[float]:
    """Return survival probabilities for months 1..n_months."""
    registry = ModelRegistry.get()

    # Strategy 1: Loaded parquet data — exact bucket
    if registry.survival_curves and bucket_id in registry.survival_curves:
        curve = registry.survival_curves[bucket_id]
        if len(curve) >= n_months:
            return curve[:n_months]
        # Pad with extrapolation if parquet is shorter than requested
        return _extend_curve(curve, n_months)

    # Strategy 2: Average curve from loaded data
    if registry.survival_curves:
        avg = _average_curve(registry.survival_curves, n_months)
        if avg:
            return avg

    # Strategy 3: Generate from hazard rate formula
    return _generate_stub_curve(bucket_id, n_months)


def _generate_stub_curve(bucket_id: int, n_months: int) -> list[float]:
    """Formula-based stub: S(t) = exp(-lambda * t)."""
    annual_hazard = _HAZARD_RATES.get(bucket_id, _DEFAULT_HAZARD)
    monthly_hazard = annual_hazard / 12
    return [math.exp(-monthly_hazard * m) for m in range(1, n_months + 1)]


def _average_curve(
    curves: dict[int, list[float]], n_months: int
) -> list[float] | None:
    """Average all loaded curves to produce a fallback."""
    if not curves:
        return None
    all_curves = list(curves.values())
    length = min(len(c) for c in all_curves)
    length = min(length, n_months)
    avg = []
    for i in range(length):
        avg.append(sum(c[i] for c in all_curves) / len(all_curves))
    if length < n_months:
        avg = _extend_curve(avg, n_months)
    return avg


def _extend_curve(curve: list[float], n_months: int) -> list[float]:
    """Extend a curve by continuing its tail decay rate."""
    if len(curve) >= n_months:
        return curve[:n_months]
    if len(curve) < 2:
        return curve + [curve[-1]] * (n_months - len(curve))
    # Use the last two points to estimate decay
    ratio = curve[-1] / curve[-2] if curve[-2] > 0 else 0.999
    extended = list(curve)
    while len(extended) < n_months:
        extended.append(max(extended[-1] * ratio, 0.0))
    return extended
