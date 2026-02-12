from fastapi import APIRouter

from app.services.model_service import get_model_status

router = APIRouter(tags=["models"])


@router.get("/models/status")
def get_models_status():
    """Return dynamic model status from the model registry."""
    return get_model_status()
