from fastapi import APIRouter

from app.db.connection import db_pool

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check():
    db_status = db_pool.test_connection()
    return {
        "status": "ok",
        "database": db_status,
        "models": {"status": "stub", "message": "Model loading not yet implemented"},
    }
