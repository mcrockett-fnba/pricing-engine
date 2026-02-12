from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.models.package import Package
from app.models.simulation import SimulationConfig
from app.models.valuation import PackageValuationResult
from app.services.simulation_service import run_valuation

router = APIRouter(tags=["valuation"])


class ValuationRequest(BaseModel):
    """Request body for running a valuation — inline package, no DB required."""
    package: Package
    config: Optional[SimulationConfig] = None


@router.post("/valuations/run", response_model=PackageValuationResult)
def run_valuation_endpoint(request: ValuationRequest):
    """Run a full valuation on an inline loan package.

    Accepts a package with loans and optional simulation config.
    Returns NPV, ROE, scenario analysis, and Monte Carlo distributions.
    """
    config = request.config or SimulationConfig()
    return run_valuation(request.package, config)
