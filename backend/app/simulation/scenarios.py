"""Scenario definitions — named macro parameter sets.

Maps user-facing scenario names to CoC scenario names and stress multipliers
for DEQ, default, and recovery rates.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScenarioParams:
    """Parameters for a single valuation scenario."""
    name: str
    coc_scenario: str
    deq_multiplier: float
    default_multiplier: float
    recovery_multiplier: float
    prepayment_multiplier: float = 1.0


_SCENARIOS: dict[str, ScenarioParams] = {
    "baseline": ScenarioParams(
        name="baseline",
        coc_scenario="baseline",
        deq_multiplier=1.0,
        default_multiplier=1.0,
        recovery_multiplier=1.0,
    ),
    "mild_recession": ScenarioParams(
        name="mild_recession",
        coc_scenario="mild_stress",
        deq_multiplier=1.5,
        default_multiplier=1.3,
        recovery_multiplier=0.85,
        prepayment_multiplier=0.7,
    ),
    "severe_recession": ScenarioParams(
        name="severe_recession",
        coc_scenario="severe_stress",
        deq_multiplier=2.5,
        default_multiplier=2.0,
        recovery_multiplier=0.65,
        prepayment_multiplier=0.4,
    ),
}


def get_scenario_params(name: str) -> ScenarioParams:
    """Return scenario parameters by name. Defaults to baseline if unknown."""
    return _SCENARIOS.get(name, _SCENARIOS["baseline"])


def list_scenario_names() -> list[str]:
    """Return all available scenario names."""
    return list(_SCENARIOS.keys())
