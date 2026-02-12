"""Loan segmentation service.

Assigns loans to risk buckets using ML models or rule-based fallback.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.ml.bucket_assigner import assign_bucket

# Bucket labels for display
_BUCKET_LABELS = {
    1: "Prime",
    2: "Near-Prime",
    3: "Non-Prime",
    4: "Sub-Prime",
    5: "Deep Sub-Prime",
}


@dataclass
class LoanSegment:
    loan_id: str
    bucket_id: int
    bucket_label: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "loan_id": self.loan_id,
            "bucket_id": self.bucket_id,
            "bucket_label": self.bucket_label,
        }


def segment_loan(loan: dict[str, Any]) -> LoanSegment:
    """Assign a single loan to a risk segment."""
    bucket_id = assign_bucket(loan)
    return LoanSegment(
        loan_id=str(loan.get("loan_id", "")),
        bucket_id=bucket_id,
        bucket_label=_BUCKET_LABELS.get(bucket_id, f"Bucket {bucket_id}"),
    )


def segment_loans(loans: list[dict[str, Any]]) -> list[LoanSegment]:
    """Assign a batch of loans to risk segments."""
    return [segment_loan(loan) for loan in loans]
