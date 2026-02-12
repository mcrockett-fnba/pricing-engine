"""Simulation orchestration service.

Coordinates Monte Carlo simulation runs across loans in a package,
aggregating loan-level results into a PackageValuationResult.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.models.package import Package
from app.models.simulation import SimulationConfig
from app.models.valuation import PackageValuationResult
from app.ml.model_loader import ModelRegistry
from app.simulation.engine import simulate_loan


def run_valuation(package: Package, config: SimulationConfig) -> PackageValuationResult:
    """Run full valuation for a loan package.

    Simulates each loan individually, then aggregates:
    - NPV = sum of loan PVs
    - NPV by scenario = sum per scenario across loans
    - NPV distribution = element-wise sum of loan MC distributions
    - ROE = (NPV - purchase_price) / purchase_price
    - ROE distribution and percentiles derived from NPV distribution
    """
    loan_results = [simulate_loan(loan, config) for loan in package.loans]

    # NPV by scenario: sum across loans
    npv_by_scenario: dict[str, float] = {}
    for scenario_name in config.scenarios:
        total = sum(lr.pv_by_scenario.get(scenario_name, 0.0) for lr in loan_results)
        npv_by_scenario[scenario_name] = round(total, 2)

    # Expected NPV = baseline scenario total
    expected_npv = npv_by_scenario.get("baseline", 0.0)

    # NPV distribution: element-wise sum of loan MC distributions
    # All loans should have the same number of MC runs
    npv_distribution: list[float] = []
    if loan_results and loan_results[0].pv_distribution:
        n_sims = len(loan_results[0].pv_distribution)
        # Sort each loan's distribution so we can add element-wise
        # (this is a simplification — correlated sum)
        for i in range(n_sims):
            total = sum(
                lr.pv_distribution[i] if i < len(lr.pv_distribution) else lr.expected_pv
                for lr in loan_results
            )
            npv_distribution.append(round(total, 2))
    npv_distribution.sort()

    # NPV percentiles
    npv_percentiles = _percentiles(npv_distribution)

    # Purchase price for ROE calculation
    purchase_price = package.purchase_price or package.total_upb

    # ROE calculations
    roe = (expected_npv - purchase_price) / purchase_price if purchase_price else 0.0

    # Annualized ROE: assumes weighted average remaining term
    avg_term_months = (
        sum(loan.remaining_term for loan in package.loans) / len(package.loans)
        if package.loans else 360
    )
    avg_term_years = avg_term_months / 12.0
    if avg_term_years > 0 and roe > -1.0:
        roe_annualized = (1.0 + roe) ** (1.0 / avg_term_years) - 1.0
    else:
        roe_annualized = roe

    # ROE by scenario
    roe_by_scenario: dict[str, float] = {}
    for name, npv in npv_by_scenario.items():
        roe_by_scenario[name] = round(
            (npv - purchase_price) / purchase_price if purchase_price else 0.0, 6
        )

    # ROE distribution from NPV distribution
    roe_distribution: list[float] = []
    if npv_distribution and purchase_price:
        roe_distribution = [
            round((npv - purchase_price) / purchase_price, 6)
            for npv in npv_distribution
        ]
    roe_percentiles = _percentiles(roe_distribution)

    # Model manifest
    registry = ModelRegistry.get()
    status = registry.get_status()
    model_manifest = {
        "version": status.get("version", "0.0.0"),
        "status": status.get("status", "unknown"),
    }

    return PackageValuationResult(
        package_id=package.package_id,
        package_name=package.name,
        loan_count=len(loan_results),
        total_upb=package.total_upb,
        purchase_price=purchase_price,
        expected_npv=round(expected_npv, 2),
        roe=round(roe, 6),
        roe_annualized=round(roe_annualized, 6),
        roe_by_scenario=roe_by_scenario,
        roe_distribution=roe_distribution,
        roe_percentiles=roe_percentiles,
        npv_by_scenario=npv_by_scenario,
        npv_distribution=npv_distribution,
        npv_percentiles=npv_percentiles,
        loan_results=loan_results,
        simulation_config=config,
        model_manifest=model_manifest,
        computed_at=datetime.now(timezone.utc),
    )


def _percentiles(values: list[float]) -> dict[str, float]:
    """Extract p5/p25/p50/p75/p95 from a sorted list."""
    if not values:
        return {}
    result = {}
    for label, p in [("p5", 0.05), ("p25", 0.25), ("p50", 0.50), ("p75", 0.75), ("p95", 0.95)]:
        idx = min(int(p * len(values)), len(values) - 1)
        result[label] = values[idx]
    return result
