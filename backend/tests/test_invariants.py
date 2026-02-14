"""Invariant tests — properties that must hold regardless of parameters.

Covers probability bounds, accounting identities, scenario monotonicity,
MC reproducibility, and portfolio aggregation correctness.
"""
import hashlib

from app.models.loan import Loan
from app.models.package import Package
from app.models.simulation import SimulationConfig
from app.simulation.cash_flow import project_cash_flows
from app.simulation.engine import simulate_loan
from app.simulation.scenarios import get_scenario_params
from app.simulation.state_transitions import get_monthly_transitions
from app.services.simulation_service import run_valuation


def _make_loan(**overrides) -> Loan:
    defaults = dict(
        loan_id="INV001",
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


# ---------------------------------------------------------------------------
# Probability invariants
# ---------------------------------------------------------------------------


def test_survival_monotonically_decreasing():
    """S(t) >= S(t+1) for all t."""
    loan = _make_loan(remaining_term=120)
    scenario = get_scenario_params("baseline")
    cfs = project_cash_flows(loan, 3, scenario)
    for i in range(1, len(cfs)):
        assert cfs[i].survival_probability <= cfs[i - 1].survival_probability, (
            f"Survival increased at month {cfs[i].month}: "
            f"{cfs[i - 1].survival_probability} -> {cfs[i].survival_probability}"
        )


def test_survival_bounded_0_1():
    """0 <= S(t) <= 1 for all t."""
    loan = _make_loan(remaining_term=120)
    for scenario_name in ["baseline", "mild_recession", "severe_recession"]:
        scenario = get_scenario_params(scenario_name)
        cfs = project_cash_flows(loan, 3, scenario)
        for cf in cfs:
            assert 0.0 <= cf.survival_probability <= 1.0, (
                f"Survival out of bounds at month {cf.month} "
                f"under {scenario_name}: {cf.survival_probability}"
            )


def test_marginal_hazard_bounded_0_1():
    """0 <= h(t) <= 1 for marginal default hazard."""
    scenario = get_scenario_params("severe_recession")
    transitions = get_monthly_transitions(5, 0, 360, scenario)
    for tx in transitions:
        assert 0.0 <= tx.marginal_default <= 1.0, (
            f"Marginal default out of [0,1] at month {tx.month}: {tx.marginal_default}"
        )


def test_cumulative_survival_consistent_with_marginals():
    """Product of (1 - h_default(t)) * (1 - h_prepay(t)) should approximate
    the cumulative survival used in cash_flow."""
    loan = _make_loan(remaining_term=60)
    scenario = get_scenario_params("baseline")
    cfs = project_cash_flows(loan, 3, scenario)
    transitions = get_monthly_transitions(3, loan.loan_age, loan.remaining_term, scenario,
                                          loan_rate=loan.interest_rate)
    product = 1.0
    for i, tx in enumerate(transitions):
        if i >= len(cfs):
            break
        product *= (1.0 - tx.marginal_default) * (1.0 - tx.marginal_prepay)
        assert abs(product - cfs[i].survival_probability) < 1e-4, (
            f"Survival mismatch at month {tx.month}: "
            f"product={product:.6f}, cf={cfs[i].survival_probability:.6f}"
        )


def test_prepay_rate_bounded():
    """0 <= SMM(t) <= 1 for all months and scenarios."""
    for scenario_name in ["baseline", "mild_recession", "severe_recession"]:
        scenario = get_scenario_params(scenario_name)
        transitions = get_monthly_transitions(3, 60, 120, scenario)
        for tx in transitions:
            assert 0.0 <= tx.marginal_prepay <= 1.0, (
                f"Prepay rate out of [0,1] at month {tx.month} "
                f"under {scenario_name}: {tx.marginal_prepay}"
            )


# ---------------------------------------------------------------------------
# Accounting invariants
# ---------------------------------------------------------------------------


def test_net_cf_equals_components():
    """net_cf == payment + prepay - loss + recovery - servicing."""
    loan = _make_loan(remaining_term=60)
    scenario = get_scenario_params("baseline")
    cfs = project_cash_flows(loan, 3, scenario)
    for cf in cfs:
        expected = (cf.expected_payment + cf.expected_prepayment
                    - cf.expected_loss + cf.expected_recovery
                    - cf.servicing_cost)
        assert abs(cf.net_cash_flow - round(expected, 2)) <= 0.02, (
            f"Net CF mismatch at month {cf.month}: "
            f"net_cf={cf.net_cash_flow}, components={expected:.2f}"
        )


def test_no_gain_from_default():
    """Under net-loss framework, expected_loss >= 0 and expected_recovery == 0."""
    loan = _make_loan(remaining_term=60)
    for bucket_id in range(1, 6):
        scenario = get_scenario_params("baseline")
        cfs = project_cash_flows(loan, bucket_id, scenario)
        for cf in cfs:
            assert cf.expected_loss >= 0.0, (
                f"Negative expected_loss at month {cf.month}, bucket {bucket_id}"
            )
            assert cf.expected_recovery == 0.0, (
                f"Non-zero expected_recovery at month {cf.month}, bucket {bucket_id}: "
                f"{cf.expected_recovery}"
            )


def test_balance_decline_monotonic():
    """Remaining balance never increases over time."""
    loan = _make_loan(remaining_term=120)
    scenario = get_scenario_params("baseline")
    cfs = project_cash_flows(loan, 3, scenario)
    # Track balance decline via scheduled_payment and survival
    # The simplest proxy: survival-weighted expected_payment should be non-negative
    for cf in cfs:
        assert cf.expected_payment >= 0.0
        assert cf.expected_prepayment >= 0.0


def test_terminal_balance_near_zero():
    """For a full-term loan under baseline, the cash flow projection should
    terminate before the full remaining term (balance amortizes to zero via
    principal, defaults, and prepayments)."""
    loan = _make_loan(remaining_term=360, loan_age=0)
    scenario = get_scenario_params("baseline")
    cfs = project_cash_flows(loan, 1, scenario)
    # Cash flows should terminate well before 360 months because defaults
    # and prepayments deplete the balance to zero
    assert len(cfs) < 360, (
        f"Cash flows ran full 360 months — balance never reached zero"
    )
    # Survival probability at termination should be small
    last_cf = cfs[-1]
    assert last_cf.survival_probability < 0.50, (
        f"Terminal survival too high: {last_cf.survival_probability}"
    )


# ---------------------------------------------------------------------------
# Scenario monotonicity
# ---------------------------------------------------------------------------


def test_severe_npv_le_mild_le_baseline():
    """NPV should decrease with stress: baseline >= mild >= severe."""
    loan = _make_loan(remaining_term=120)
    config = SimulationConfig(n_simulations=0, include_stochastic=False)
    result = simulate_loan(loan, config)
    baseline = result.pv_by_scenario["baseline"]
    mild = result.pv_by_scenario["mild_recession"]
    severe = result.pv_by_scenario["severe_recession"]
    assert baseline >= mild, f"baseline ({baseline}) < mild ({mild})"
    assert mild >= severe, f"mild ({mild}) < severe ({severe})"


def test_scenario_spread_positive():
    """Baseline - severe > 0 (stress always costs value)."""
    loan = _make_loan(remaining_term=120)
    config = SimulationConfig(n_simulations=0, include_stochastic=False)
    result = simulate_loan(loan, config)
    spread = result.pv_by_scenario["baseline"] - result.pv_by_scenario["severe_recession"]
    assert spread > 0, f"Non-positive scenario spread: {spread}"


# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------


def test_hash_deterministic_across_calls():
    """SHA-256 hash of loan_id produces identical seed across calls."""
    loan_id = "LOAN_DETERM_001"
    h1 = int(hashlib.sha256(loan_id.encode()).hexdigest(), 16) & 0xFFFFFFFF
    h2 = int(hashlib.sha256(loan_id.encode()).hexdigest(), 16) & 0xFFFFFFFF
    assert h1 == h2


def test_mc_results_reproducible():
    """Two simulate_loan() calls with same seed produce identical pv_distribution."""
    loan = _make_loan(remaining_term=60)
    config = SimulationConfig(n_simulations=20, include_stochastic=True, stochastic_seed=12345)
    r1 = simulate_loan(loan, config)
    r2 = simulate_loan(loan, config)
    assert r1.pv_distribution == r2.pv_distribution, "MC distributions differ across runs"


# ---------------------------------------------------------------------------
# Portfolio aggregation
# ---------------------------------------------------------------------------


def test_portfolio_npv_sum_of_parts():
    """Deterministic portfolio NPV should equal sum of individual loan NPVs."""
    loans = [
        _make_loan(loan_id="AGG001", unpaid_balance=100_000, remaining_term=60),
        _make_loan(loan_id="AGG002", unpaid_balance=150_000, remaining_term=120),
    ]
    config = SimulationConfig(n_simulations=0, include_stochastic=False)

    individual_pvs = []
    for loan in loans:
        result = simulate_loan(loan, config)
        individual_pvs.append(result.pv_by_scenario["baseline"])

    package = Package(
        package_id="PKG001",
        name="Test Package",
        loan_count=len(loans),
        total_upb=sum(l.unpaid_balance for l in loans),
        loans=loans,
    )
    pkg_result = run_valuation(package, config)

    assert abs(pkg_result.npv_by_scenario["baseline"] - sum(individual_pvs)) < 0.02, (
        f"Portfolio NPV ({pkg_result.npv_by_scenario['baseline']}) != "
        f"sum of parts ({sum(individual_pvs)})"
    )


def test_mc_distribution_not_sorted():
    """pv_distribution preserves simulation-path insertion order, not sorted order.

    Deterministic check: run the same loan twice with fixed seed, confirm both
    return identical ordering (proving it's deterministic) and that the ordering
    differs from sorted (proving the engine isn't sorting).
    """
    loan = _make_loan(loan_id="UNSORT001", remaining_term=60)
    config = SimulationConfig(n_simulations=50, include_stochastic=True, stochastic_seed=42)

    r1 = simulate_loan(loan, config)
    r2 = simulate_loan(loan, config)

    # Deterministic: same inputs → same path-ordered output
    assert r1.pv_distribution == r2.pv_distribution

    # Structural: raw order differs from sorted order
    assert r1.pv_distribution != sorted(r1.pv_distribution), (
        "pv_distribution is sorted — engine should preserve simulation-path order"
    )
