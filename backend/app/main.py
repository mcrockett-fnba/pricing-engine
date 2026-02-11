from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.connection import db_pool
from app.api.routes import health, packages, valuation, models


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize DB pool
    db_pool.initialize()
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
