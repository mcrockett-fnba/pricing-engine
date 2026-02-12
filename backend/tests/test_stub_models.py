"""Tests for stub models — DEQ, default, recovery, cost-of-capital."""
import pytest

from app.ml.stub_deq import get_deq_rate
from app.ml.stub_default import get_default_probability, get_loss_severity
from app.ml.stub_recovery import (
    get_recovery_rate,
    get_recovery_amount,
    get_foreclosure_timeline,
    is_judicial_state,
)
from app.ml.stub_cost_of_capital import (
    get_scenario,
    list_scenarios,
    get_monthly_discount_rate,
)


# --- DEQ tests ---

def test_deq_seasoning_decreases():
    """DEQ rate should decrease as loan ages (seasoning effect)."""
    rate_new = get_deq_rate(3, loan_age=0)
    rate_old = get_deq_rate(3, loan_age=60)
    assert rate_new > rate_old


def test_deq_riskier_buckets_higher():
    """Higher-risk buckets should have higher DEQ rates at same age."""
    age = 12
    rates = [get_deq_rate(bid, age) for bid in range(1, 6)]
    for i in range(len(rates) - 1):
        assert rates[i] < rates[i + 1]


def test_deq_rate_positive():
    """DEQ rates should always be positive."""
    for bid in range(1, 6):
        for age in (0, 12, 60, 120, 360):
            assert get_deq_rate(bid, age) > 0


# --- Default model tests ---

def test_default_severity_progression():
    """Default probability should increase with DPD severity."""
    tiers = ["current", "30dpd", "60dpd", "90dpd", "120dpd", "150dpd", "180dpd"]
    probs = [get_default_probability(t) for t in tiers]
    for i in range(len(probs) - 1):
        assert probs[i] <= probs[i + 1], f"{tiers[i]} should be <= {tiers[i+1]}"


def test_default_current_is_zero():
    assert get_default_probability("current") == 0.0


def test_loss_severity_range():
    """Loss severity should be between 0 and 1 for all buckets."""
    for bid in range(1, 6):
        sev = get_loss_severity(bid)
        assert 0 < sev < 1


def test_loss_severity_increases_with_risk():
    """Riskier buckets should have higher loss severity."""
    severities = [get_loss_severity(bid) for bid in range(1, 6)]
    for i in range(len(severities) - 1):
        assert severities[i] <= severities[i + 1]


# --- Recovery model tests ---

def test_recovery_rate_range():
    for bid in range(1, 6):
        rate = get_recovery_rate(bid)
        assert 0 < rate < 1


def test_recovery_amount_calculation():
    amt = get_recovery_amount(1, 100_000)
    rate = get_recovery_rate(1)
    assert amt == 100_000 * rate


def test_foreclosure_timeline_judicial():
    assert get_foreclosure_timeline("NY") == 24
    assert is_judicial_state("FL") is True


def test_foreclosure_timeline_non_judicial():
    assert get_foreclosure_timeline("TX") == 12
    assert is_judicial_state("CA") is False


# --- Cost of Capital tests ---

def test_coc_four_scenarios():
    names = list_scenarios()
    assert len(names) == 4
    assert "baseline" in names
    assert "mild_stress" in names
    assert "severe_stress" in names
    assert "low_rate" in names


def test_coc_baseline_values():
    s = get_scenario("baseline")
    assert s.discount_rate == 0.08
    assert s.cost_of_funds == 0.045
    assert s.required_return == 0.12


def test_coc_monthly_discount():
    monthly = get_monthly_discount_rate("baseline")
    assert abs(monthly - 0.08 / 12) < 1e-10


def test_coc_unknown_scenario_defaults_to_baseline():
    s = get_scenario("nonexistent")
    assert s.name == "baseline"
