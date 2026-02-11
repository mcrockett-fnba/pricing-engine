from datetime import date
from typing import Optional

from pydantic import BaseModel


class LoanSummary(BaseModel):
    loan_id: str
    unpaid_balance: float
    interest_rate: float
    credit_score: Optional[int] = None
    ltv: Optional[float] = None


class Loan(BaseModel):
    loan_id: str
    unpaid_balance: float
    interest_rate: float
    original_term: int
    remaining_term: int
    loan_age: int
    credit_score: Optional[int] = None
    ltv: Optional[float] = None
    dti: Optional[float] = None
    property_type: Optional[str] = None
    occupancy_type: Optional[str] = None
    state: Optional[str] = None
    origination_date: Optional[date] = None
