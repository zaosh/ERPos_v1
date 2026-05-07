import logging
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from config import settings
from middleware.logging import LoggingMiddleware, PIILogFilter
from middleware.security import SecurityMiddleware
from routes import auth, items, sales, analytics, health, jobs
from routes import customers, returns

logging.basicConfig(level=settings.LOG_LEVEL)
logging.getLogger().addFilter(PIILogFilter())
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    logger.info("Redis connection pool initialized")

    yield

    await app.state.redis.aclose()
    logger.info("Redis connection pool closed")


app = FastAPI(
    title="ThriftOS API",
    version="2.0.0",
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
app.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
app.include_router(customers.router, prefix="/customers", tags=["customers"])
app.include_router(returns.router, prefix="/returns", tags=["returns"])

if not settings.is_production:
    from pathlib import Path
    image_dir = Path(settings.IMAGE_STORAGE_PATH)
    image_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/images", StaticFiles(directory=str(image_dir)), name="images")
