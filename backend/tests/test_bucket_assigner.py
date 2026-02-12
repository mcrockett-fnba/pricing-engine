"""Tests for bucket_assigner — all 5 buckets, fallback behavior."""
import pytest

from app.ml.model_loader import ModelRegistry
from app.ml.bucket_assigner import assign_bucket


@pytest.fixture(autouse=True)
def _reset_registry():
    ModelRegistry.reset()
    yield
    ModelRegistry.reset()


@pytest.mark.parametrize(
    "credit_score, ltv, expected_bucket",
    [
        (780, 0.60, 1),   # Prime
        (720, 0.75, 2),   # Near-Prime
        (680, 0.85, 3),   # Non-Prime
        (620, 0.95, 4),   # Sub-Prime
        (550, 1.10, 5),   # Deep Sub-Prime
    ],
)
def test_assign_all_five_buckets(credit_score, ltv, expected_bucket):
    """Each bucket boundary is correctly assigned via hardcoded fallback."""
    loan = {"credit_score": credit_score, "ltv": ltv}
    assert assign_bucket(loan) == expected_bucket


def test_missing_features_falls_to_catchall():
    """Loan with no features lands in the catch-all bucket (5)."""
    assert assign_bucket({}) == 5


def test_missing_ltv_skips_non_matching():
    """Loan with only credit_score — ltv rule fails, falls through."""
    loan = {"credit_score": 800}
    # Has high credit_score but no ltv, so no rules fully match → catch-all
    assert assign_bucket(loan) == 5


def test_uses_json_rules_when_loaded(tmp_path):
    """When bucket_definitions are loaded, they override hardcoded rules."""
    import json
    survival_dir = tmp_path / "survival"
    survival_dir.mkdir()
    # Custom rules: only one bucket, catch-all = bucket 99
    defs = {
        "buckets": [
            {"bucket_id": 99, "label": "Custom", "rules": []},
        ]
    }
    (survival_dir / "bucket_definitions.json").write_text(json.dumps(defs))

    reg = ModelRegistry.get()
    reg.load(tmp_path)
    assert assign_bucket({"credit_score": 750, "ltv": 0.5}) == 99


def test_boundary_values():
    """Test exact boundary values — >= and < operators."""
    # Exactly at Prime boundary
    assert assign_bucket({"credit_score": 740, "ltv": 0.69}) == 1
    # ltv exactly at 0.70 → fails Prime, tries Near-Prime
    assert assign_bucket({"credit_score": 740, "ltv": 0.70}) == 2
