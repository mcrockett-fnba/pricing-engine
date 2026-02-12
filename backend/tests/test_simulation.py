"""Tests for the simulation engine — scenarios, PMT, cash flows, Monte Carlo."""
import math

from app.models.loan import Loan
from app.models.simulation import SimulationConfig
from app.simulation.scenarios import get_scenario_params, list_scenario_names
from app.simulation.cash_flow import calculate_monthly_payment, project_cash_flows
from app.simulation.state_transitions import get_monthly_transitions
from app.simulation.engine import simulate_loan


def _make_loan(**overrides) -> Loan:
    defaults = dict(
        loan_id="L001",
        unpaid_balance=200_000.0,
        interest_rate=0.065,
        original_term=360,
        remaining_term=300,
        loan_age=60,
        credit_score=720,
        ltv=0.75,
    )
    defaults.update(overrides)
    return Loan(**defaults)


# --- Scenario tests ---


def test_scenario_baseline_has_unit_multipliers():
    s = get_scenario_params("baseline")
    assert s.deq_multiplier == 1.0
    assert s.default_multiplier == 1.0
    assert s.recovery_multiplier == 1.0
    assert s.coc_scenario == "baseline"


def test_scenario_severe_recession_has_stress_multipliers():
    s = get_scenario_params("severe_recession")
    assert s.deq_multiplier > 1.0
    assert s.default_multiplier > 1.0
    assert s.recovery_multiplier < 1.0
    assert s.coc_scenario == "severe_stress"


def test_unknown_scenario_defaults_to_baseline():
    s = get_scenario_params("nonexistent_scenario")
    assert s.name == "baseline"


def test_list_scenario_names_returns_all_three():
    names = list_scenario_names()
    assert set(names) == {"baseline", "mild_recession", "severe_recession"}


# --- PMT formula tests ---


def test_pmt_known_value():
    # $200k at 6% for 360 months ≈ $1,199.10
    pmt = calculate_monthly_payment(200_000, 0.06, 360)
    assert abs(pmt - 1199.10) < 1.0


def test_pmt_zero_rate():
    pmt = calculate_monthly_payment(120_000, 0.0, 120)
    assert abs(pmt - 1000.0) < 0.01


def test_pmt_zero_balance():
    assert calculate_monthly_payment(0, 0.05, 360) == 0.0


def test_pmt_zero_term():
    assert calculate_monthly_payment(100_000, 0.05, 0) == 0.0


# --- Cash flow projection tests ---


def test_cash_flows_length_close_to_term():
    loan = _make_loan(remaining_term=60)
    scenario = get_scenario_params("baseline")
    cfs = project_cash_flows(loan, 2, scenario)
    # May be slightly shorter if balance amortizes to 0 before final month
    assert len(cfs) >= 55
    assert len(cfs) <= 60


def test_cash_flows_first_month_is_one():
    loan = _make_loan(remaining_term=60)
    scenario = get_scenario_params("baseline")
    cfs = project_cash_flows(loan, 2, scenario)
    assert cfs[0].month == 1


def test_cash_flows_pv_positive():
    loan = _make_loan(remaining_term=60)
    scenario = get_scenario_params("baseline")
    cfs = project_cash_flows(loan, 2, scenario)
    total_pv = sum(cf.present_value for cf in cfs)
    assert total_pv > 0


# --- State transition tests ---


def test_transitions_length():
    scenario = get_scenario_params("baseline")
    transitions = get_monthly_transitions(3, 60, 120, scenario)
    assert len(transitions) == 120


def test_stressed_transitions_have_higher_defaults():
    baseline = get_scenario_params("baseline")
    severe = get_scenario_params("severe_recession")
    t_base = get_monthly_transitions(3, 60, 12, baseline)
    t_severe = get_monthly_transitions(3, 60, 12, severe)
    # Severe recession should have higher marginal default in month 1
    assert t_severe[0].marginal_default >= t_base[0].marginal_default


# --- Monte Carlo engine tests ---


def test_simulate_loan_returns_result():
    loan = _make_loan(remaining_term=60)
    config = SimulationConfig(n_simulations=5, include_stochastic=True, stochastic_seed=42)
    result = simulate_loan(loan, config)
    assert result.loan_id == "L001"
    assert result.bucket_id in range(1, 6)
    assert result.expected_pv > 0
    assert "baseline" in result.pv_by_scenario


def test_deterministic_reproducibility():
    loan = _make_loan(remaining_term=60)
    config = SimulationConfig(n_simulations=0, include_stochastic=False)
    r1 = simulate_loan(loan, config)
    r2 = simulate_loan(loan, config)
    assert r1.expected_pv == r2.expected_pv
    assert r1.pv_by_scenario == r2.pv_by_scenario


def test_mc_distribution_populated():
    loan = _make_loan(remaining_term=36)
    config = SimulationConfig(n_simulations=10, include_stochastic=True, stochastic_seed=42)
    result = simulate_loan(loan, config)
    # 3 scenarios × 10 sims = 30 MC runs
    assert len(result.pv_distribution) == 30
    assert result.pv_distribution == sorted(result.pv_distribution)


def test_mc_reproducible_with_seed():
    loan = _make_loan(remaining_term=36)
    config = SimulationConfig(n_simulations=10, include_stochastic=True, stochastic_seed=99)
    r1 = simulate_loan(loan, config)
    r2 = simulate_loan(loan, config)
    assert r1.pv_distribution == r2.pv_distribution


def test_stress_scenarios_produce_lower_pv():
    loan = _make_loan(remaining_term=60)
    config = SimulationConfig(n_simulations=0, include_stochastic=False)
    result = simulate_loan(loan, config)
    baseline_pv = result.pv_by_scenario["baseline"]
    severe_pv = result.pv_by_scenario["severe_recession"]
    assert severe_pv < baseline_pv


def test_percentiles_present_when_mc_enabled():
    loan = _make_loan(remaining_term=36)
    config = SimulationConfig(n_simulations=10, include_stochastic=True, stochastic_seed=42)
    result = simulate_loan(loan, config)
    for key in ("p5", "p25", "p50", "p75", "p95"):
        assert key in result.pv_percentiles
    assert result.pv_percentiles["p5"] <= result.pv_percentiles["p95"]
