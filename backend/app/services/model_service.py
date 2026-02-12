"""Model management service.

Facade for model loading, status, bucket assignment, and survival curves.
"""
from __future__ import annotations

import logging
from typing import Any

from app.ml.model_loader import ModelRegistry
from app.ml.bucket_assigner import assign_bucket
from app.ml.curve_provider import get_survival_curve

logger = logging.getLogger(__name__)


def initialize_models(model_dir: str | None = None) -> None:
    """Load all model artifacts at startup."""
    registry = ModelRegistry.get()
    registry.load(model_dir)
    logger.info("Models initialized — status: %s", registry.get_status().get("status"))


def get_model_status() -> dict[str, Any]:
    """Return current model registry status for API consumption."""
    return ModelRegistry.get().get_status()


def assign_loan_bucket(loan: dict[str, Any]) -> int:
    """Assign a single loan to a risk bucket (1-5)."""
    return assign_bucket(loan)


def get_loan_survival_curve(bucket_id: int, n_months: int = 360) -> list[float]:
    """Get survival curve for a given bucket."""
    return get_survival_curve(bucket_id, n_months)
