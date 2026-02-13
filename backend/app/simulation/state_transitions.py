"""Loan state transition model — Markov-style monthly transitions.

Derives monthly survival, default, DEQ, loss severity, and recovery
from the ML stub models, applying scenario stress multipliers.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.ml.curve_provider import get_survival_curve
from app.ml.stub_deq import get_deq_rate
from app.ml.stub_default import get_loss_severity
from app.ml.stub_prepayment import get_prepay_hazard
from app.ml.stub_recovery import get_recovery_rate
from app.simulation.scenarios import ScenarioParams


@dataclass
class MonthlyTransition:
    """Transition probabilities and rates for a single month."""
    month: int
    survival_prob: float
    marginal_default: float
    marginal_prepay: float
    deq_rate: float
    loss_severity: float
    recovery_rate: float


def get_monthly_transitions(
    bucket_id: int,
    loan_age: int,
    remaining_term: int,
    scenario: ScenarioParams,
    loan_rate: float = 0.065,
) -> list[MonthlyTransition]:
    """Build per-month transition vector for a loan.

    Uses the survival curve to derive marginal default hazard:
        h(t) = 1 - S(t)/S(t-1)
    Then applies scenario stress multipliers to DEQ, default, and recovery.
    """
    curve = get_survival_curve(bucket_id, remaining_term)
    base_loss_severity = get_loss_severity(bucket_id)
    base_recovery = get_recovery_rate(bucket_id)

    transitions: list[MonthlyTransition] = []
    for m in range(remaining_term):
        month_num = m + 1
        current_age = loan_age + m

        # Survival and marginal default from curve
        s_curr = curve[m]
        s_prev = curve[m - 1] if m > 0 else 1.0
        marginal_default = max(1.0 - s_curr / s_prev, 0.0) if s_prev > 0 else 0.0

        # DEQ rate from stub model
        deq = get_deq_rate(bucket_id, current_age)

        # Prepayment hazard from stub model
        base_prepay = get_prepay_hazard(bucket_id, current_age, loan_rate)

        # Apply scenario stress multipliers
        stressed_default = min(marginal_default * scenario.default_multiplier, 1.0)
        stressed_deq = min(deq * scenario.deq_multiplier, 1.0)
        stressed_recovery = min(base_recovery * scenario.recovery_multiplier, 1.0)
        stressed_prepay = min(base_prepay * scenario.prepayment_multiplier, 1.0)

        transitions.append(MonthlyTransition(
            month=month_num,
            survival_prob=s_curr,
            marginal_default=stressed_default,
            marginal_prepay=stressed_prepay,
            deq_rate=stressed_deq,
            loss_severity=base_loss_severity,
            recovery_rate=stressed_recovery,
        ))

    return transitions
