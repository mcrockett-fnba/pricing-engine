"""Stub DEQ (delinquency) model — formula-based, no trained artifact.

DEQ rate = base_rate × exp(-0.02 × loan_age)
Higher-risk buckets have higher base rates; seasoning reduces delinquency.
"""
from __future__ import annotations

import math

# Base annual DEQ rates by bucket
_BASE_RATES = {
    1: 0.01,   # Prime
    2: 0.025,  # Near-Prime
    3: 0.05,   # Non-Prime
    4: 0.10,   # Sub-Prime
    5: 0.18,   # Deep Sub-Prime
}
_DEFAULT_BASE = 0.05
_SEASONING_DECAY = 0.02


def get_deq_rate(bucket_id: int, loan_age: int) -> float:
    """Return monthly delinquency rate for a bucket at a given loan age (months).

    Seasoning effect: rate declines exponentially as loan ages.
    """
    base = _BASE_RATES.get(bucket_id, _DEFAULT_BASE)
    monthly_base = base / 12
    seasoning = math.exp(-_SEASONING_DECAY * loan_age)
    return monthly_base * seasoning
