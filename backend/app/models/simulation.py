from enum import Enum
from typing import Optional

from pydantic import BaseModel


class ValuationTrack(str, Enum):
    """Which valuation track to run."""
    A = "A"
    B = "B"
    both = "both"


class TrackAConfig(BaseModel):
    """Configuration for Track A (APEX2-compatible) valuation."""
    target_yield: float = 0.07
    annual_cdr: float = 0.0015
    recovery_rate: float = 0.50
    treasury_10y: float = 4.5
    seasoning_ramp_months: int = 30


class SimulationConfig(BaseModel):
    """Configuration for Monte Carlo simulation runs."""
    n_simulations: int = 5
    scenarios: list[str] = ["baseline", "mild_recession", "severe_recession"]
    include_stochastic: bool = True
    stochastic_seed: Optional[int] = 42
    track: ValuationTrack = ValuationTrack.B
    track_a_config: Optional[TrackAConfig] = None
