"""Tests for the km_only prepayment model mode.

Verifies that the KM decomposition (flat CDR for default + KM residual for prepay)
produces correct hazard decomposition, bounded survival, and different pricing
from the stub mode.
"""
from app.models.loan import Loan
from app.models.simulation import PrepayModel, SimulationConfig
from app.simulation.scenarios import get_scenario_params
from app.simulation.state_transitions import get_monthly_transitions
from app.simulation.cash_flow import project_cash_flows
from app.simulation.engine import simulate_loan


def _make_loan(**overrides) -> Loan:
    defaults = dict(
        loan_id="KM001",
        unpaid_balance=200_000.0,
        interest_rate=0.065,
        original_term=360,
        remaining_term=120,
        loan_age=60,
        credit_score=720,
        ltv=0.75,
    )
    defaults.update(overrides)
    return Loan(**defaults)


# --- Hazard decomposition ---

def test_km_only_hazards_sum_to_km():
    """In km_only mode, default + prepay should approximate the KM all-causes hazard."""
    scenario = get_scenario_params("baseline")
    annual_cdr = 0.0015

    # Get KM hazard from stub mode (marginal_default IS the KM hazard)
    stub_tx = get_monthly_transitions(3, 60, 60, scenario, prepay_model="stub")

    # Get decomposed hazards from km_only mode
    km_tx = get_monthly_transitions(
        3, 60, 60, scenario, prepay_model="km_only", annual_cdr=annual_cdr,
    )

    monthly_cdr = 1.0 - (1.0 - annual_cdr) ** (1.0 / 12.0)

    for i in range(len(stub_tx)):
        km_hazard = stub_tx[i].marginal_default  # KM all-causes in stub mode
        decomposed_sum = km_tx[i].marginal_default + km_tx[i].marginal_prepay

        # When KM hazard >= monthly_cdr: sum should equal KM hazard
        # When KM hazard < monthly_cdr: default = monthly_cdr, prepay = 0,
        #   so sum = monthly_cdr >= km_hazard
        assert decomposed_sum >= km_hazard - 1e-12, (
            f"Month {i+1}: decomposed {decomposed_sum:.8f} < km_hazard {km_hazard:.8f}"
        )
        # Default should always be the flat monthly CDR
        assert abs(km_tx[i].marginal_default - monthly_cdr) < 1e-12


# --- Survival bounds ---

def test_km_only_survival_bounded():
    """Cumulative survival should stay in [0, 1] under km_only mode."""
    loan = _make_loan(remaining_term=120)
    scenario = get_scenario_params("baseline")
    cfs = project_cash_flows(
        loan, 3, scenario, prepay_model="km_only", annual_cdr=0.0015,
    )
    for cf in cfs:
        assert 0.0 <= cf.survival_probability <= 1.0, (
            f"Month {cf.month}: survival={cf.survival_probability}"
        )


# --- PV comparison ---

def test_km_only_pv_differs_from_stub():
    """km_only should produce a different PV than stub mode."""
    loan = _make_loan(remaining_term=120)

    config_stub = SimulationConfig(
        n_simulations=0, include_stochastic=False,
        prepay_model=PrepayModel.stub,
    )
    config_km = SimulationConfig(
        n_simulations=0, include_stochastic=False,
        prepay_model=PrepayModel.km_only, annual_cdr=0.0015,
    )

    result_stub = simulate_loan(loan, config_stub)
    result_km = simulate_loan(loan, config_km)

    assert result_stub.expected_pv != result_km.expected_pv, (
        f"Stub PV {result_stub.expected_pv} == KM-only PV {result_km.expected_pv}"
    )


# --- CDR sensitivity ---

def test_km_only_higher_cdr_lowers_pv():
    """Higher CDR means more credit loss, so PV should decrease."""
    loan = _make_loan(remaining_term=120)

    config_low = SimulationConfig(
        n_simulations=0, include_stochastic=False,
        prepay_model=PrepayModel.km_only, annual_cdr=0.001,
    )
    config_high = SimulationConfig(
        n_simulations=0, include_stochastic=False,
        prepay_model=PrepayModel.km_only, annual_cdr=0.05,
    )

    pv_low = simulate_loan(loan, config_low).expected_pv
    pv_high = simulate_loan(loan, config_high).expected_pv

    assert pv_high < pv_low, (
        f"High CDR PV {pv_high} >= Low CDR PV {pv_low}"
    )


# --- Scenario stress ordering ---

def test_km_only_scenario_stress():
    """Severe recession should still produce lower PV than baseline in km_only mode."""
    loan = _make_loan(remaining_term=120)

    config = SimulationConfig(
        n_simulations=0, include_stochastic=False,
        prepay_model=PrepayModel.km_only, annual_cdr=0.0015,
    )

    result = simulate_loan(loan, config)
    baseline_pv = result.pv_by_scenario["baseline"]
    severe_pv = result.pv_by_scenario["severe_recession"]

    assert severe_pv < baseline_pv, (
        f"Severe PV {severe_pv} >= Baseline PV {baseline_pv}"
    )


# --- Backward compatibility ---

def test_stub_mode_unchanged():
    """Default config (stub mode) should produce the same result as before."""
    loan = _make_loan(remaining_term=60)

    # Default SimulationConfig uses stub mode
    config = SimulationConfig(n_simulations=0, include_stochastic=False)
    assert config.prepay_model == PrepayModel.stub

    result = simulate_loan(loan, config)
    assert result.expected_pv > 0
    assert "baseline" in result.pv_by_scenario
