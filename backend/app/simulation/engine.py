"""Monte Carlo simulation engine.

Runs N simulations per scenario for a set of loans, producing
LoanValuationResult with deterministic PVs, MC distributions, and percentiles.
"""
from __future__ import annotations

import math
import random

from app.models.loan import Loan
from app.models.simulation import SimulationConfig
from app.models.valuation import LoanValuationResult
from app.ml.bucket_assigner import assign_bucket
from app.ml.model_loader import ModelRegistry
from app.simulation.scenarios import get_scenario_params
from app.simulation.cash_flow import project_cash_flows

_MC_SIGMA = 0.15  # Lognormal shock standard deviation


def _generate_shocks(
    n_months: int, rng: random.Random,
) -> list[dict[str, float]]:
    """Generate per-month lognormal shock multipliers for MC perturbation."""
    shocks = []
    for _ in range(n_months):
        shocks.append({
            "deq": math.exp(rng.gauss(0, _MC_SIGMA)),
            "default": math.exp(rng.gauss(0, _MC_SIGMA)),
            "recovery": math.exp(rng.gauss(0, _MC_SIGMA)),
            "prepay": math.exp(rng.gauss(0, _MC_SIGMA)),
        })
    return shocks


def _sum_pv(cash_flows) -> float:
    """Sum present values from a list of MonthlyCashFlow."""
    return sum(cf.present_value for cf in cash_flows)


def simulate_loan(loan: Loan, config: SimulationConfig) -> LoanValuationResult:
    """Run deterministic + Monte Carlo simulation for a single loan.

    For each scenario in config.scenarios:
      1. Run deterministic cash flow projection
      2. Run N stochastic simulations with lognormal shocks
    Aggregate into PV distribution, percentiles, and per-scenario PVs.
    """
    loan_dict = loan.model_dump()
    bucket_id = assign_bucket(loan_dict)

    pv_by_scenario: dict[str, float] = {}
    all_mc_pvs: list[float] = []
    baseline_cash_flows = []

    for scenario_name in config.scenarios:
        scenario = get_scenario_params(scenario_name)

        # Deterministic run
        det_cfs = project_cash_flows(loan, bucket_id, scenario)
        det_pv = _sum_pv(det_cfs)
        pv_by_scenario[scenario_name] = round(det_pv, 2)

        if scenario_name == "baseline":
            baseline_cash_flows = det_cfs

            # Monte Carlo runs — baseline scenario only for clean distribution
            if config.include_stochastic and config.n_simulations > 0:
                if config.stochastic_seed is not None:
                    base_seed = config.stochastic_seed
                    loan_hash = hash(loan.loan_id) & 0xFFFFFFFF
                    seed = (base_seed + loan_hash) & 0xFFFFFFFF
                    rng = random.Random(seed)
                else:
                    rng = random.Random()

                for _ in range(config.n_simulations):
                    shocks = _generate_shocks(loan.remaining_term, rng)
                    mc_cfs = project_cash_flows(loan, bucket_id, scenario, shocks)
                    all_mc_pvs.append(round(_sum_pv(mc_cfs), 2))

    # Sort MC distribution for percentile extraction
    all_mc_pvs.sort()

    # Percentiles
    pv_percentiles: dict[str, float] = {}
    if all_mc_pvs:
        for p_label, p_val in [("p5", 0.05), ("p25", 0.25), ("p50", 0.50), ("p75", 0.75), ("p95", 0.95)]:
            idx = min(int(p_val * len(all_mc_pvs)), len(all_mc_pvs) - 1)
            pv_percentiles[p_label] = all_mc_pvs[idx]

    # Expected PV = baseline deterministic
    expected_pv = pv_by_scenario.get("baseline", 0.0)

    # Model status
    registry = ModelRegistry.get()
    model_status = {}
    status_info = registry.get_status()
    if "models" in status_info:
        for name, info in status_info["models"].items():
            model_status[name] = info.get("status", "unknown")
    else:
        model_status["overall"] = status_info.get("status", "unknown")

    return LoanValuationResult(
        loan_id=loan.loan_id,
        bucket_id=bucket_id,
        expected_pv=expected_pv,
        pv_by_scenario=pv_by_scenario,
        pv_distribution=all_mc_pvs,
        pv_percentiles=pv_percentiles,
        monthly_cash_flows=baseline_cash_flows,
        model_status=model_status,
    )
