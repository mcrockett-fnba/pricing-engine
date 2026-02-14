from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.models.simulation import SimulationConfig


class ModelProvenance(BaseModel):
    """Tracks which model/track produced a valuation result."""
    track: str
    track_a_version: Optional[str] = None
    track_b_version: Optional[str] = None
    prepayment_source: Optional[str] = None
    credit_model: Optional[str] = None
    discount_method: Optional[str] = None
    discount_rate_annual: Optional[float] = None


class CalibrationMetrics(BaseModel):
    """Calibration comparison between Track A and Track B."""
    track_a_pv: Optional[float] = None
    track_b_pv: Optional[float] = None
    absolute_error: Optional[float] = None
    relative_error_pct: Optional[float] = None
    roe_a: Optional[float] = None
    roe_b: Optional[float] = None
    roe_diff_bps: Optional[float] = None
    within_tolerance: Optional[bool] = None
    tolerance_threshold_pct: Optional[float] = None


class MonthlyCashFlow(BaseModel):
    """Projected cash flow for a single month."""
    month: int
    scheduled_payment: float
    survival_probability: float
    expected_payment: float
    deq_probability: float
    default_probability: float
    expected_loss: float
    expected_recovery: float
    prepay_probability: float = 0.0
    expected_prepayment: float = 0.0
    servicing_cost: float
    net_cash_flow: float
    discount_factor: float
    present_value: float


class LoanValuationResult(BaseModel):
    """Valuation result for a single loan."""
    loan_id: str
    bucket_id: int
    expected_pv: float
    pv_by_scenario: dict[str, float]
    pv_distribution: list[float]
    pv_percentiles: dict[str, float]
    monthly_cash_flows: list[MonthlyCashFlow]
    model_status: dict[str, str]
    provenance: Optional[ModelProvenance] = None
    calibration: Optional[CalibrationMetrics] = None


class PackageValuationResult(BaseModel):
    """Aggregated valuation result for a loan package."""
    package_id: str
    package_name: str
    loan_count: int
    total_upb: float
    purchase_price: Optional[float] = None
    expected_npv: float
    roe: float
    roe_annualized: float
    roe_by_scenario: dict[str, float]
    roe_distribution: list[float]
    roe_percentiles: dict[str, float]
    npv_by_scenario: dict[str, float]
    npv_distribution: list[float]
    npv_percentiles: dict[str, float]
    loan_results: list[LoanValuationResult]
    simulation_config: SimulationConfig
    model_manifest: dict
    computed_at: datetime
    provenance: Optional[ModelProvenance] = None
    calibration_summary: Optional[CalibrationMetrics] = None
    tolerance_gate_passed: Optional[bool] = None
