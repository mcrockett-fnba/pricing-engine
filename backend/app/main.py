from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.connection import db_pool
from app.services.model_service import initialize_models
from app.api.routes import health, packages, valuation, models, prepayment, segmentation


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize DB pool and load models
    db_pool.initialize()
    initialize_models()
    yield
    # Shutdown: close DB pool
    db_pool.close()


app = FastAPI(title="Pricing Engine", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(packages.router, prefix="/api")
app.include_router(valuation.router, prefix="/api")
app.include_router(models.router, prefix="/api")
app.include_router(prepayment.router, prefix="/api")
app.include_router(segmentation.router, prefix="/api")
