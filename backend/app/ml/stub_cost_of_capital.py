"""Stub cost-of-capital model — flat rates + named scenarios.

Four scenarios: baseline, mild_stress, severe_stress, low_rate.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CoCScenario:
    name: str
    discount_rate: float       # annual
    cost_of_funds: float       # annual
    required_return: float     # annual


_SCENARIOS: dict[str, CoCScenario] = {
    "baseline": CoCScenario(
        name="baseline",
        discount_rate=0.08,
        cost_of_funds=0.045,
        required_return=0.12,
    ),
    "mild_stress": CoCScenario(
        name="mild_stress",
        discount_rate=0.10,
        cost_of_funds=0.055,
        required_return=0.15,
    ),
    "severe_stress": CoCScenario(
        name="severe_stress",
        discount_rate=0.14,
        cost_of_funds=0.075,
        required_return=0.20,
    ),
    "low_rate": CoCScenario(
        name="low_rate",
        discount_rate=0.05,
        cost_of_funds=0.025,
        required_return=0.08,
    ),
}


def get_scenario(name: str = "baseline") -> CoCScenario:
    """Return a named CoC scenario. Defaults to baseline."""
    return _SCENARIOS.get(name, _SCENARIOS["baseline"])


def list_scenarios() -> list[str]:
    """Return available scenario names."""
    return list(_SCENARIOS.keys())


def get_monthly_discount_rate(scenario_name: str = "baseline") -> float:
    """Return the monthly discount rate for a scenario."""
    s = get_scenario(scenario_name)
    return s.discount_rate / 12
