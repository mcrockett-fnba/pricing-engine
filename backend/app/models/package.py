from datetime import date
from typing import Optional

from pydantic import BaseModel

from app.models.loan import Loan


class PackageSummary(BaseModel):
    package_id: str
    name: str
    loan_count: int
    total_upb: float
    purchase_price: Optional[float] = None
    purchase_date: Optional[date] = None


class Package(BaseModel):
    package_id: str
    name: str
    loan_count: int
    total_upb: float
    purchase_price: Optional[float] = None
    purchase_date: Optional[date] = None
    loans: list[Loan] = []
