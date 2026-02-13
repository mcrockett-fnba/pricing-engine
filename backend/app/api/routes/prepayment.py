"""Prepayment analysis API route."""
from fastapi import APIRouter

from app.models.prepayment import (
    PrepaymentAnalysisResult,
    PrepaymentConfig,
    PrepaymentRequest,
)
from app.services.prepayment_analysis import run_prepayment_analysis

router = APIRouter(tags=["prepayment"])


@router.post("/prepayment/analyze", response_model=PrepaymentAnalysisResult)
def analyze_prepayment(request: PrepaymentRequest):
    """Run APEX2 prepayment analysis on an inline loan package."""
    config = request.config or PrepaymentConfig()
    return run_prepayment_analysis(request.package, config)
