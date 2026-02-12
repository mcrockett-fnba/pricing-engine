"""Bucket assigner — maps a Loan to a bucket_id using ML model or rules.

3-tier fallback strategy:
1. XGBoost .predict() (if model.pkl loaded)
2. Rules from bucket_definitions.json (operator-based condition matching)
3. Hardcoded fallback (same 5-bucket logic, no files needed)
"""
from __future__ import annotations

import logging
import operator
from typing import Any

from app.ml.model_loader import ModelRegistry

logger = logging.getLogger(__name__)

_OPS = {
    ">=": operator.ge,
    ">": operator.gt,
    "<=": operator.le,
    "<": operator.lt,
    "==": operator.eq,
    "!=": operator.ne,
}

# Hardcoded fallback — same logic as the generated bucket_definitions.json
_HARDCODED_BUCKETS = [
    {"bucket_id": 1, "label": "Prime",
     "rules": [{"feature": "credit_score", "operator": ">=", "value": 740},
               {"feature": "ltv", "operator": "<", "value": 0.70}]},
    {"bucket_id": 2, "label": "Near-Prime",
     "rules": [{"feature": "credit_score", "operator": ">=", "value": 700},
               {"feature": "ltv", "operator": "<", "value": 0.80}]},
    {"bucket_id": 3, "label": "Non-Prime",
     "rules": [{"feature": "credit_score", "operator": ">=", "value": 660},
               {"feature": "ltv", "operator": "<", "value": 0.90}]},
    {"bucket_id": 4, "label": "Sub-Prime",
     "rules": [{"feature": "credit_score", "operator": ">=", "value": 600},
               {"feature": "ltv", "operator": "<", "value": 1.00}]},
    {"bucket_id": 5, "label": "Deep Sub-Prime", "rules": []},
]


def assign_bucket(loan: dict[str, Any]) -> int:
    """Return bucket_id (1-5) for a loan dict.

    Loan dict should have at minimum: credit_score, ltv.
    """
    registry = ModelRegistry.get()

    # Strategy 1: XGBoost model
    if registry.xgb_model is not None:
        try:
            bucket_id = _assign_via_xgb(registry.xgb_model, loan)
            if bucket_id is not None:
                return bucket_id
        except Exception as e:
            logger.warning("XGBoost prediction failed, falling back: %s", e)

    # Strategy 2: JSON rule definitions
    if registry.bucket_definitions:
        return _assign_via_rules(registry.bucket_definitions, loan)

    # Strategy 3: Hardcoded rules
    return _assign_via_rules(_HARDCODED_BUCKETS, loan)


def _assign_via_xgb(model: Any, loan: dict[str, Any]) -> int | None:
    """Use XGBoost model to predict bucket. Returns None on failure."""
    features = [loan.get("credit_score", 0), loan.get("ltv", 1.0)]
    prediction = model.predict([features])
    return int(prediction[0])


def _assign_via_rules(buckets: list[dict], loan: dict[str, Any]) -> int:
    """Match loan against ordered bucket rules. First match wins; last bucket is catch-all."""
    for bucket in buckets:
        rules = bucket.get("rules", [])
        if not rules:
            # Catch-all bucket
            return bucket["bucket_id"]
        if _matches_all_rules(rules, loan):
            return bucket["bucket_id"]

    # Should not reach here if buckets include a catch-all, but be safe
    return buckets[-1]["bucket_id"] if buckets else 5


def _matches_all_rules(rules: list[dict], loan: dict[str, Any]) -> bool:
    """Return True if loan satisfies every rule in the list."""
    for rule in rules:
        feature = rule["feature"]
        op_str = rule["operator"]
        threshold = rule["value"]
        loan_value = loan.get(feature)
        if loan_value is None:
            return False
        op_fn = _OPS.get(op_str)
        if op_fn is None:
            logger.warning("Unknown operator %r in rule", op_str)
            return False
        if not op_fn(loan_value, threshold):
            return False
    return True
