"""
Storage service abstraction — local filesystem today, S3 tomorrow.
Switch by setting STORAGE_BACKEND=s3 in config.
"""
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

import redis.asyncio as aioredis

from config import settings

logger = logging.getLogger(__name__)

MAGIC_BYTES = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG": "image/png",
}
MAX_FILE_SIZE = 10 * 1024 * 1024
THUMBNAIL_SIZE = (300, 300)


@runtime_checkable
class StorageBackend(Protocol):
    async def save_temp(self, image_bytes: bytes, user_id: int, redis_client: aioredis.Redis) -> str: ...
    async def claim(self, temp_id: str, user_id: int, item_id: int, redis_client: aioredis.Redis) -> tuple[str, str]: ...
    async def duplicate(self, src_path: str, item_id: int) -> tuple[str, str]: ...
    async def delete(self, path: str) -> None: ...
    def url(self, path: Optional[str]) -> Optional[str]: ...


class LocalStorage:
    """Wraps the existing filesystem image storage logic."""

    async def save_temp(self, image_bytes: bytes, user_id: int, redis_client: aioredis.Redis) -> str:
        import uuid
        temp_id = str(uuid.uuid4())
        temp_dir = Path(settings.IMAGE_STORAGE_PATH) / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / f"{temp_id}.jpg"
        _write_normalized_jpeg(image_bytes, str(temp_path))
        payload = json.dumps({"path": str(temp_path), "uploaded_by": user_id})
        await redis_client.set(f"temp_image:{temp_id}", payload, ex=settings.TEMP_IMAGE_TTL_SECONDS)
        return temp_id

    async def claim(self, temp_id: str, user_id: int, item_id: int, redis_client: aioredis.Redis) -> tuple[str, str]:
        from fastapi import HTTPException
        raw = await redis_client.get(f"temp_image:{temp_id}")
        if raw is None:
            raise HTTPException(status_code=410, detail="Temp image expired or not found")
        data = json.loads(raw)
        if data["uploaded_by"] != user_id:
            raise HTTPException(status_code=403, detail="Image belongs to a different user")

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        final_dir = Path(settings.IMAGE_STORAGE_PATH) / str(now.year) / f"{now.month:02d}"
        final_dir.mkdir(parents=True, exist_ok=True)

        image_path = str(final_dir / f"{item_id}.jpg")
        thumb_path = str(final_dir / f"{item_id}_thumb.jpg")
        os.rename(data["path"], image_path)
        _create_thumbnail(image_path, thumb_path)
        await redis_client.delete(f"temp_image:{temp_id}")
        return image_path, thumb_path

    async def duplicate(self, src_path: str, item_id: int) -> tuple[str, str]:
        """Copy an existing image to a new item-specific path."""
        src = Path(src_path)
        dest_dir = src.parent
        image_path = str(dest_dir / f"{item_id}.jpg")
        thumb_path = str(dest_dir / f"{item_id}_thumb.jpg")
        shutil.copy2(src_path, image_path)
        _create_thumbnail(image_path, thumb_path)
        return image_path, thumb_path

    async def delete(self, path: str) -> None:
        try:
            os.unlink(path)
        except OSError as e:
            logger.warning(f"Failed to delete file {path}: {e}")

    def url(self, path: Optional[str]) -> Optional[str]:
        if not path:
            return None
        base = Path(settings.IMAGE_STORAGE_PATH)
        try:
            rel = Path(path).relative_to(base)
            return f"{settings.IMAGE_BASE_URL}/{rel}"
        except ValueError:
            return None


class S3Storage:
    """Stub for future S3 backend. Implement with boto3 when STORAGE_BACKEND=s3."""

    def __init__(self) -> None:
        raise NotImplementedError("S3Storage not yet implemented. Set STORAGE_BACKEND=local.")

    async def save_temp(self, image_bytes: bytes, user_id: int, redis_client: aioredis.Redis) -> str:
        raise NotImplementedError

    async def claim(self, temp_id: str, user_id: int, item_id: int, redis_client: aioredis.Redis) -> tuple[str, str]:
        raise NotImplementedError

    async def duplicate(self, src_path: str, item_id: int) -> tuple[str, str]:
        raise NotImplementedError

    async def delete(self, path: str) -> None:
        raise NotImplementedError

    def url(self, path: Optional[str]) -> Optional[str]:
        raise NotImplementedError


_storage_instance: Optional[LocalStorage] = None


def get_storage() -> LocalStorage:
    global _storage_instance
    if _storage_instance is None:
        backend = getattr(settings, "STORAGE_BACKEND", "local")
        if backend == "s3":
            _storage_instance = S3Storage()  # type: ignore[assignment]
        else:
            _storage_instance = LocalStorage()
    return _storage_instance  # type: ignore[return-value]


# ── Image helpers (shared between backends) ────────────────────────────────────

def _write_normalized_jpeg(image_bytes: bytes, dest_path: str) -> None:
    import io
    from PIL import Image
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    max_dim = 1920
    if img.width > max_dim or img.height > max_dim:
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)
    img.save(dest_path, format="JPEG", quality=90)


def _create_thumbnail(source_path: str, dest_path: str) -> None:
    from PIL import Image
    img = Image.open(source_path).convert("RGB")
    img.thumbnail(THUMBNAIL_SIZE, Image.LANCZOS)
    thumb = Image.new("RGB", THUMBNAIL_SIZE, (255, 255, 255))
    offset = ((THUMBNAIL_SIZE[0] - img.width) // 2, (THUMBNAIL_SIZE[1] - img.height) // 2)
    thumb.paste(img, offset)
    thumb.save(dest_path, format="JPEG", quality=85)
