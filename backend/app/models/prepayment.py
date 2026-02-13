"""Pydantic request/response models for prepayment analysis."""
from typing import Optional

from pydantic import BaseModel

from app.models.package import Package


class PrepaymentConfig(BaseModel):
    treasury_10y: float = 4.5
    seasoning_ramp_months: int = 30


class PrepaymentRequest(BaseModel):
    package: Package
    config: Optional[PrepaymentConfig] = None


class PrepaymentSummary(BaseModel):
    loan_count: int
    total_upb: float
    wtd_avg_rate: float
    wtd_avg_credit: float
    wtd_avg_ltv: float
    wtd_avg_seasoning: float
    wtd_avg_remaining_term: float
    treasury_10y: float


class ScenarioResult(BaseModel):
    label: str
    multiplier_source: str
    method: str
    nper_months: Optional[float] = None
    monthly_months: float
    nper_years: Optional[float] = None
    monthly_years: float


class CreditBandRow(BaseModel):
    band: str
    loan_count: int
    total_upb: float
    avg_multiplier: float
    avg_credit_multiplier: float
    avg_rate: float
    effective_life_months: float


class SeasoningSensitivityPoint(BaseModel):
    assumed_age_months: int
    effective_life_months: float
    effective_life_years: float


class LoanMultiplierDetail(BaseModel):
    loan_id: str
    credit_band: str
    dim_credit: float
    rate_delta_band: str
    dim_rate_delta: float
    ltv_band: str
    dim_ltv: float
    loan_size_band: str
    dim_loan_size: float
    avg_4dim: float


class PrepaymentAnalysisResult(BaseModel):
    summary: PrepaymentSummary
    scenarios: list[ScenarioResult]
    credit_bands: list[CreditBandRow]
    seasoning_sensitivity: list[SeasoningSensitivityPoint]
    loan_details: list[LoanMultiplierDetail]
