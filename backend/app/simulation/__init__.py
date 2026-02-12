"""Simulation engine — scenarios, transitions, cash flows, and Monte Carlo."""
from app.simulation.scenarios import get_scenario_params, list_scenario_names, ScenarioParams
from app.simulation.state_transitions import get_monthly_transitions, MonthlyTransition
from app.simulation.cash_flow import project_cash_flows, calculate_monthly_payment
from app.simulation.engine import simulate_loan

__all__ = [
    "ScenarioParams",
    "get_scenario_params",
    "list_scenario_names",
    "MonthlyTransition",
    "get_monthly_transitions",
    "project_cash_flows",
    "calculate_monthly_payment",
    "simulate_loan",
]
