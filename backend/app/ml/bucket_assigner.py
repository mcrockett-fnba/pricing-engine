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
    """Return bucket_id for a loan dict.

    If segmentation tree is loaded, returns leaf_id (1-75+).
    Otherwise falls back to 5-bucket system (1-5).
    Loan dict should have at minimum: credit_score, ltv.
    """
    registry = ModelRegistry.get()

    # Strategy 0: Segmentation tree (top priority)
    if registry.segmentation_tree is not None:
        try:
            bucket_id = _assign_via_segmentation_tree(registry, loan)
            if bucket_id is not None:
                return bucket_id
        except Exception as e:
            logger.warning("Segmentation tree assignment failed, falling back: %s", e)

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


def _assign_via_segmentation_tree(registry: "ModelRegistry", loan: dict[str, Any]) -> int | None:
    """Use segmentation tree to predict leaf_id.

    Maps Loan model fields to training feature scale:
      - interest_rate: decimal (0.072) → percent (7.2) via ×100
      - ltv: decimal (0.80) → percent (80) via ×100
      - credit_score → creditScore
      - unpaid_balance → loanSize
      - origination_date.year → noteDateYear (default 2021)
      - state → stateGroup via mapping (default middle bin)
      - dti default 36, ITIN default 0, origCustAmortMonth = original_term (default 360)
    """
    import numpy as np

    state_mapping = registry.state_group_mapping
    median_bin = max(state_mapping.values()) // 2 if state_mapping else 3

    # Map loan fields to training features (order must match FEATURE_COLS)
    state_str = str(loan.get("state", "")) if loan.get("state") else ""
    state_group = state_mapping.get(state_str, median_bin)

    origination_date = loan.get("origination_date")
    if origination_date is not None:
        try:
            note_year = origination_date.year
        except AttributeError:
            note_year = 2021
    else:
        note_year = 2021

    features = np.array([[
        note_year,                                                # noteDateYear
        loan.get("credit_score") or 700,                          # creditScore
        loan.get("dti") or 36.0,                                  # dti
        (loan.get("ltv") or 0.80) * 100,                          # ltv (decimal → percent)
        (loan.get("interest_rate") or 0.07) * 100,                # interestRate (decimal → percent)
        loan.get("unpaid_balance", 200000),                       # loanSize
        state_group,                                              # stateGroup
        loan.get("ITIN", 0),                                     # ITIN
        loan.get("original_term") or 360,                         # origCustAmortMonth
    ]])

    node_id = registry.segmentation_tree.apply(features)[0]
    node_to_leaf = registry.tree_structure.get("node_to_leaf", {})

    # node_to_leaf keys are strings in JSON
    leaf_id = node_to_leaf.get(str(node_id))
    if leaf_id is None:
        logger.warning("Node %d not found in node_to_leaf mapping", node_id)
        return None

    return int(leaf_id)


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
