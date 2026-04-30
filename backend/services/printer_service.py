import asyncio
import json
import logging
from decimal import Decimal
from typing import Optional

import redis.asyncio as aioredis

from config import settings

logger = logging.getLogger(__name__)

_PRINT_QUEUE_KEY = "print_queue"


def build_zpl_label(
    barcode: str,
    price: Decimal,
    category: str,
    color: Optional[str],
    size: Optional[str],
) -> str:
    color_str = color or "?"
    size_str = size or "?"
    price_str = f"${price:.2f}"
    description = f"{price_str} | {category} | {color_str} | {size_str}"

    return (
        "^XA\n"
        "^FO10,10^BY2^BCN,60,Y,N,N"
        f"^FD{barcode}^FS\n"
        f"^FO10,80^A0N,20,20^FD{description}^FS\n"
        "^XZ"
    )


async def print_label(zpl: str, item_id: int, barcode: str, redis_client: aioredis.Redis) -> bool:
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(settings.PRINTER_HOST, settings.PRINTER_PORT),
            timeout=settings.PRINTER_TIMEOUT,
        )
        writer.write(zpl.encode())
        await writer.drain()
        writer.close()
        await writer.wait_closed()
        logger.info(f"Label printed: {barcode}")
        return True
    except (OSError, asyncio.TimeoutError) as e:
        logger.warning(f"Printer offline, queuing label for {barcode}: {e}")
        await _queue_print_job(zpl, item_id, barcode, redis_client)
        return False


async def _queue_print_job(zpl: str, item_id: int, barcode: str, redis_client: aioredis.Redis) -> None:
    job = json.dumps({
        "item_id": item_id,
        "barcode": barcode,
        "zpl": zpl,
        "attempts": 0,
    })
    await redis_client.rpush(_PRINT_QUEUE_KEY, job)


async def drain_print_queue(ctx: dict) -> int:
    """ARQ background task — attempts to print queued labels."""
    redis_client: aioredis.Redis = ctx.get("redis")
    if redis_client is None:
        return 0

    jobs_raw = await redis_client.lrange(_PRINT_QUEUE_KEY, 0, -1)
    if not jobs_raw:
        return 0

    await redis_client.delete(_PRINT_QUEUE_KEY)

    printed = 0
    for raw in jobs_raw:
        job = json.loads(raw)
        attempts = job.get("attempts", 0)
        zpl = job["zpl"]
        barcode = job["barcode"]
        item_id = job["item_id"]

        if attempts >= settings.PRINT_QUEUE_MAX_ATTEMPTS:
            logger.error(f"Print job permanently failed after {attempts} attempts: {barcode}")
            continue

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(settings.PRINTER_HOST, settings.PRINTER_PORT),
                timeout=settings.PRINTER_TIMEOUT,
            )
            writer.write(zpl.encode())
            await writer.drain()
            writer.close()
            await writer.wait_closed()
            printed += 1
            logger.info(f"Queued label printed: {barcode}")
        except (OSError, asyncio.TimeoutError):
            job["attempts"] = attempts + 1
            await redis_client.rpush(_PRINT_QUEUE_KEY, json.dumps(job))

    return printed
