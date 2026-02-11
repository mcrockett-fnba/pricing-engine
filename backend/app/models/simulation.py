from typing import Optional

from pydantic import BaseModel


class SimulationConfig(BaseModel):
    """Configuration for Monte Carlo simulation runs."""
    n_simulations: int = 500
    scenarios: list[str] = ["baseline", "mild_recession", "severe_recession"]
    include_stochastic: bool = True
    stochastic_seed: Optional[int] = 42
