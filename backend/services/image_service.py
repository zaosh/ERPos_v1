import json
import logging
import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import UploadFile, HTTPException
from PIL import Image
import redis.asyncio as aioredis

from config import settings

logger = logging.getLogger(__name__)

MAGIC_BYTES = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG": "image/png",
}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
THUMBNAIL_SIZE = (300, 300)


async def validate_image(file: UploadFile) -> bytes:
    content = await file.read()

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=422, detail="Image exceeds 10MB limit")

    if len(content) < 4:
        raise HTTPException(status_code=422, detail="Invalid image file")

    matched = False
    for magic, mime in MAGIC_BYTES.items():
        if content[: len(magic)] == magic:
            matched = True
            break

    if not matched:
        raise HTTPException(status_code=422, detail="Only JPEG and PNG images are accepted")

    return content


async def save_temp_image(image_bytes: bytes, user_id: int, redis_client: aioredis.Redis) -> str:
    temp_id = str(uuid.uuid4())
    temp_dir = Path(settings.IMAGE_STORAGE_PATH) / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    temp_path = temp_dir / f"{temp_id}.jpg"
    _write_normalized_jpeg(image_bytes, str(temp_path))

    payload = json.dumps({"path": str(temp_path), "uploaded_by": user_id})
    await redis_client.set(f"temp_image:{temp_id}", payload, ex=settings.TEMP_IMAGE_TTL_SECONDS)

    return temp_id


async def claim_temp_image(
    temp_image_id: str, user_id: int, item_id: int, redis_client: aioredis.Redis
) -> tuple[str, str]:
    raw = await redis_client.get(f"temp_image:{temp_image_id}")
    if raw is None:
        raise HTTPException(status_code=410, detail="Temp image expired or not found")

    data = json.loads(raw)
    if data["uploaded_by"] != user_id:
        raise HTTPException(status_code=403, detail="Image belongs to a different user")

    source_path = data["path"]

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    final_dir = Path(settings.IMAGE_STORAGE_PATH) / str(now.year) / f"{now.month:02d}"
    final_dir.mkdir(parents=True, exist_ok=True)

    image_path = str(final_dir / f"{item_id}.jpg")
    thumb_path = str(final_dir / f"{item_id}_thumb.jpg")

    os.rename(source_path, image_path)
    _create_thumbnail(image_path, thumb_path)

    await redis_client.delete(f"temp_image:{temp_image_id}")

    return image_path, thumb_path


def _write_normalized_jpeg(image_bytes: bytes, dest_path: str) -> None:
    import io
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    max_dim = 1920
    if img.width > max_dim or img.height > max_dim:
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)
    img.save(dest_path, format="JPEG", quality=90)


def _create_thumbnail(source_path: str, dest_path: str) -> None:
    img = Image.open(source_path).convert("RGB")
    img.thumbnail(THUMBNAIL_SIZE, Image.LANCZOS)

    thumb = Image.new("RGB", THUMBNAIL_SIZE, (255, 255, 255))
    offset = ((THUMBNAIL_SIZE[0] - img.width) // 2, (THUMBNAIL_SIZE[1] - img.height) // 2)
    thumb.paste(img, offset)
    thumb.save(dest_path, format="JPEG", quality=85)


def get_image_url(image_path: Optional[str]) -> Optional[str]:
    if not image_path:
        return None
    base = Path(settings.IMAGE_STORAGE_PATH)
    try:
        rel = Path(image_path).relative_to(base)
        return f"{settings.IMAGE_BASE_URL}/{rel}"
    except ValueError:
        return None


async def cleanup_expired_temp_images(ctx: dict) -> int:
    """ARQ background task — removes temp images older than 15 minutes."""
    import time
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
