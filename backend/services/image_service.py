"""
Image service — thin wrapper around storage_service.get_storage().
All filesystem/S3 logic lives in storage_service.py.
"""
import logging
import time
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, UploadFile
import redis.asyncio as aioredis

from services.storage_service import get_storage, MAGIC_BYTES, MAX_FILE_SIZE

logger = logging.getLogger(__name__)


async def validate_image(file: UploadFile) -> bytes:
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=422, detail="Image exceeds 10MB limit")
    if len(content) < 4:
        raise HTTPException(status_code=422, detail="Invalid image file")
    matched = any(content[: len(magic)] == magic for magic in MAGIC_BYTES)
    if not matched:
        raise HTTPException(status_code=422, detail="Only JPEG and PNG images are accepted")
    return content


async def save_temp_image(image_bytes: bytes, user_id: int, redis_client: aioredis.Redis) -> str:
    return await get_storage().save_temp(image_bytes, user_id, redis_client)


async def claim_temp_image(
    temp_image_id: str, user_id: int, item_id: int, redis_client: aioredis.Redis
) -> tuple[str, str]:
    return await get_storage().claim(temp_image_id, user_id, item_id, redis_client)


def get_image_url(path: Optional[str]) -> Optional[str]:
    return get_storage().url(path)


async def cleanup_expired_temp_images(ctx: dict) -> int:
    """ARQ background task — removes temp images older than 15 minutes."""
    from config import settings
    temp_dir = Path(settings.IMAGE_STORAGE_PATH) / "temp"
    if not temp_dir.exists():
        return 0
    removed = 0
    cutoff = time.time() - 900
    for f in temp_dir.glob("*.jpg"):
        if f.stat().st_mtime < cutoff:
            f.unlink(missing_ok=True)
            removed += 1
    if removed:
        logger.info(f"Cleaned up {removed} expired temp images")
    return removed
