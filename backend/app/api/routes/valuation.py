from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["valuation"])


@router.post("/valuations/run")
def run_valuation():
    """Stub — valuation engine not yet implemented."""
    return JSONResponse(
        status_code=501,
        content={"detail": "Valuation engine not yet implemented"},
    )
