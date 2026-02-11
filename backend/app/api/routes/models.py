from fastapi import APIRouter

router = APIRouter(tags=["models"])


@router.get("/models/status")
def get_model_status():
    """Stub — returns hardcoded model status until model loader is implemented."""
    return {
        "models": {
            "survival": {"status": "stub", "version": "0.0.1"},
            "deq": {"status": "stub", "version": "0.0.1"},
            "default": {"status": "stub", "version": "0.0.1"},
            "recovery": {"status": "stub", "version": "0.0.1"},
        }
    }
