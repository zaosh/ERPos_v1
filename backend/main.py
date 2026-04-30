import logging
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from config import settings
from middleware.logging import LoggingMiddleware
from middleware.security import SecurityMiddleware
from routes import auth, items, sales, analytics, health
from services.cv_service import load_cv_model

logging.basicConfig(level=settings.LOG_LEVEL)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    logger.info("Redis connection pool initialized")

    try:
        await load_cv_model()
    except Exception as e:
        logger.warning(f"CV model load failed (non-fatal): {e}")

    yield

    await app.state.redis.aclose()
    logger.info("Redis connection pool closed")


app = FastAPI(
    title="ThriftOS API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url=None,
)

app.add_middleware(LoggingMiddleware)
app.add_middleware(
    SecurityMiddleware,
    allowed_origins=settings.allowed_origins_list,
    is_production=settings.is_production,
)

app.include_router(health.router)
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(items.router, prefix="/items", tags=["items"])
app.include_router(sales.router, prefix="/sales", tags=["sales"])
app.include_router(analytics.router, prefix="/analytics", tags=["analytics"])

if not settings.is_production:
    import os
    from pathlib import Path
    image_dir = Path(settings.IMAGE_STORAGE_PATH)
    image_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/images", StaticFiles(directory=str(image_dir)), name="images")
