from fastapi import APIRouter

from app.db.connection import db_pool
from app.ml.model_loader import ModelRegistry

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check():
    db_status = db_pool.test_connection()
    registry = ModelRegistry.get()
    model_status = {"status": "loaded"} if registry.is_loaded else {"status": "not_loaded"}
    return {
        "status": "ok",
        "database": db_status,
        "models": model_status,
    }
