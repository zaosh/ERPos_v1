from fastapi import APIRouter, Request
from database import check_db_connection
from services.cv_service import _model_loaded

router = APIRouter()


@router.get("/health")
async def health_check(request: Request):
    db_ok = await check_db_connection()

    redis_ok = False
    try:
        redis_client = request.app.state.redis
        await redis_client.ping()
        redis_ok = True
    except Exception:
        pass

    return {
        "status": "ok",
        "db": "ok" if db_ok else "error",
        "redis": "ok" if redis_ok else "error",
        "cv_model_loaded": _model_loaded,
    }
