"""Cash flow projector — projects monthly cash flows for a single loan.

Produces a list of MonthlyCashFlow objects using standard amortization (PMT)
and survival-weighted expected values from the state transition model.
"""
from __future__ import annotations

from app.models.loan import Loan
from app.models.valuation import MonthlyCashFlow
from app.simulation.scenarios import ScenarioParams
from app.simulation.state_transitions import get_monthly_transitions
from app.ml.stub_cost_of_capital import get_monthly_discount_rate

_SERVICING_COST_ANNUAL = 0.0025  # 25 bps annual


def calculate_monthly_payment(balance: float, annual_rate: float, remaining_months: int) -> float:
    """Standard PMT formula for a fixed-rate amortizing loan.

    PMT = P * r / (1 - (1+r)^-n)
    """
    if remaining_months <= 0 or balance <= 0:
        return 0.0
    r = annual_rate / 12.0
    if r <= 0:
        return balance / remaining_months
    return balance * r / (1.0 - (1.0 + r) ** -remaining_months)


def project_cash_flows(
    loan: Loan,
    bucket_id: int,
    scenario: ScenarioParams,
    stochastic_shocks: list[dict[str, float]] | None = None,
) -> list[MonthlyCashFlow]:
    """Project monthly cash flows for a single loan under a scenario.

    Args:
        loan: Loan with balance, rate, terms.
        bucket_id: Risk bucket (1-5).
        scenario: Scenario parameters with stress multipliers.
        stochastic_shocks: Optional per-month multiplier dicts with keys
            'deq', 'default', 'recovery' for Monte Carlo perturbation.

    Returns:
        List of MonthlyCashFlow for each month of remaining term.
    """
    transitions = get_monthly_transitions(
        bucket_id, loan.loan_age, loan.remaining_term, scenario,
    )

    monthly_discount = get_monthly_discount_rate(scenario.coc_scenario)
    monthly_servicing = _SERVICING_COST_ANNUAL / 12.0
    balance = loan.unpaid_balance
    pmt = calculate_monthly_payment(balance, loan.interest_rate, loan.remaining_term)

    cash_flows: list[MonthlyCashFlow] = []
    cumulative_survival = 1.0

    for i, tx in enumerate(transitions):
        if balance <= 0:
            break

        # Apply stochastic shocks if provided
        marginal_default = tx.marginal_default
        deq_rate = tx.deq_rate
        recovery_rate = tx.recovery_rate
        if stochastic_shocks and i < len(stochastic_shocks):
            shock = stochastic_shocks[i]
            marginal_default = min(marginal_default * shock.get("default", 1.0), 1.0)
            deq_rate = min(deq_rate * shock.get("deq", 1.0), 1.0)
            recovery_rate = min(recovery_rate * shock.get("recovery", 1.0), 1.0)

        # Survival probability decays by marginal default each month
        cumulative_survival *= (1.0 - marginal_default)

        # Scheduled payment (may be less than PMT if balance is small)
        scheduled = min(pmt, balance * (1.0 + loan.interest_rate / 12.0))

        # Survival-weighted expected payment
        expected_payment = scheduled * cumulative_survival

        # Expected loss = default_prob * LGD * balance * survival_entering_month
        survival_entering = cumulative_survival / (1.0 - marginal_default) if marginal_default < 1.0 else 0.0
        expected_loss = marginal_default * tx.loss_severity * balance * survival_entering

        # Expected recovery on defaulted amount
        expected_recovery = marginal_default * recovery_rate * balance * survival_entering

        # Servicing cost on surviving balance
        servicing_cost = balance * monthly_servicing * cumulative_survival

        # Net cash flow
        net_cf = expected_payment - expected_loss + expected_recovery - servicing_cost

        # Discount factor: 1 / (1+r)^t
        discount_factor = 1.0 / (1.0 + monthly_discount) ** tx.month
        present_value = net_cf * discount_factor

        cash_flows.append(MonthlyCashFlow(
            month=tx.month,
            scheduled_payment=round(scheduled, 2),
            survival_probability=round(cumulative_survival, 6),
            expected_payment=round(expected_payment, 2),
            deq_probability=round(deq_rate, 6),
            default_probability=round(marginal_default, 6),
            expected_loss=round(expected_loss, 2),
            expected_recovery=round(expected_recovery, 2),
            servicing_cost=round(servicing_cost, 2),
            net_cash_flow=round(net_cf, 2),
            discount_factor=round(discount_factor, 6),
            present_value=round(present_value, 2),
        ))

        # Amortize: reduce balance by principal portion and defaults
        interest_payment = balance * loan.interest_rate / 12.0
        principal_payment = scheduled - interest_payment
        default_loss = marginal_default * balance * survival_entering
        balance = max(balance - principal_payment - default_loss, 0.0)

    return cash_flows
