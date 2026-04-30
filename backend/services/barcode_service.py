import io
import logging
import re
from datetime import datetime, timezone

import redis.asyncio as aioredis

from config import settings

logger = logging.getLogger(__name__)

_BARCODE_PATTERN = re.compile(r"^THR-\d{8}-\d{5}$")


async def generate_barcode(redis_client: aioredis.Redis) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    counter_key = f"barcode_seq:{today}"

    await redis_client.set(counter_key, 0, ex=172800, nx=True)
    n = await redis_client.incr(counter_key)

    return f"{settings.BARCODE_PREFIX}-{today}-{n:05d}"


def generate_barcode_image(barcode_str: str) -> bytes:
    try:
        import barcode
        from barcode.writer import ImageWriter

        code = barcode.get("code128", barcode_str, writer=ImageWriter())
        buf = io.BytesIO()
        code.write(buf)
        return buf.getvalue()
    except Exception as e:
        logger.warning(f"Barcode image generation failed: {e}")
        return b""


def validate_barcode_format(barcode: str) -> bool:
    return bool(_BARCODE_PATTERN.match(barcode))
