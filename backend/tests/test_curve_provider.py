"""Tests for curve_provider — stub curves: length, monotonicity, ordering."""
import pytest

from app.ml.model_loader import ModelRegistry
from app.ml.curve_provider import get_survival_curve


@pytest.fixture(autouse=True)
def _reset_registry():
    ModelRegistry.reset()
    yield
    ModelRegistry.reset()


def test_stub_curve_length():
    """Default stub curve has 360 months."""
    curve = get_survival_curve(1)
    assert len(curve) == 360


def test_stub_curve_custom_length():
    """Requesting fewer months returns shorter curve."""
    curve = get_survival_curve(1, n_months=120)
    assert len(curve) == 120


def test_stub_curve_monotonic_decreasing():
    """Survival probability should be monotonically decreasing."""
    curve = get_survival_curve(3)
    for i in range(1, len(curve)):
        assert curve[i] <= curve[i - 1], f"Month {i+1} increased from {i}"


def test_stub_curve_bucket_ordering():
    """Riskier buckets should have lower survival at any given month."""
    curves = {bid: get_survival_curve(bid) for bid in range(1, 6)}
    # Check at month 60 (5 years)
    for bid in range(1, 5):
        assert curves[bid][59] >= curves[bid + 1][59], (
            f"Bucket {bid} should survive better than {bid+1} at month 60"
        )


def test_stub_curve_reasonable_values():
    """Survival probabilities should be between 0 and 1."""
    for bid in range(1, 6):
        curve = get_survival_curve(bid)
        assert curve[0] > 0.99, "First month should be near 1.0"
        assert curve[-1] > 0.0, "Last month should be > 0"
        assert all(0 <= p <= 1.0 for p in curve)


def test_loaded_curves_take_precedence(tmp_path):
    """When parquet data is loaded, it's used instead of stubs."""
    import math
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        pytest.skip("pyarrow not installed")

    survival_dir = tmp_path / "survival"
    survival_dir.mkdir()
    # Create a tiny parquet with only bucket 1, 10 months
    bucket_ids = [1] * 10
    months = list(range(1, 11))
    probs = [math.exp(-0.001 * m) for m in months]
    table = pa.table({
        "bucket_id": pa.array(bucket_ids, type=pa.int32()),
        "month": pa.array(months, type=pa.int32()),
        "survival_prob": pa.array(probs, type=pa.float64()),
    })
    pq.write_table(table, str(survival_dir / "survival_curves.parquet"))

    reg = ModelRegistry.get()
    reg.load(tmp_path)

    curve = get_survival_curve(1, n_months=10)
    assert len(curve) == 10
    # Values should match what we wrote
    for i, expected in enumerate(probs):
        assert abs(curve[i] - expected) < 1e-10
