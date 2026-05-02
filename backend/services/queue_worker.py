"""
Queue worker — standalone async process.
Run: python services/queue_worker.py
Two instances run in parallel via docker-compose deploy.replicas.
SKIP LOCKED in get_next_job ensures they never process the same job.
"""
import asyncio
import logging
import os
import sys

# Allow imports from backend root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import settings
from models.item import Item, ItemType
from models.job_queue import JobStatus, JobType
from services.cv_service import quick_analyze, deep_analyze, analyze_fashion, detect_color
from services.printer_service import send_label, PrinterOfflineError, PrinterTimeoutError, PrinterError
from services.queue_service import (
    RetryableError, PermanentError,
    get_next_job, complete_job, fail_job,
)

logging.basicConfig(level=settings.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("queue_worker")

_engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=5,
    max_overflow=5,
    pool_pre_ping=True,
)
_SessionFactory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


# ─── Dispatcher ───────────────────────────────────────────────────────────────

async def _dispatch(db: AsyncSession, job) -> dict:
    payload = job.payload or {}

    if job.job_type == JobType.cv_phase_a:
        return await _run_phase_a(db, job.item_id, payload)

    elif job.job_type == JobType.cv_phase_b:
        return await _run_phase_b(db, job.item_id, payload)

    elif job.job_type == JobType.fashion_attributes:
        return await _run_fashion(db, job.item_id, payload)

    elif job.job_type in (JobType.print_label, JobType.print_retry):
        return await _run_print(job.item_id, payload)

    else:
        raise PermanentError(f"Unknown job_type: {job.job_type}")


async def _run_phase_a(db: AsyncSession, item_id: int, payload: dict) -> dict:
    image_path = payload.get("image_path")
    if not image_path:
        raise PermanentError("cv_phase_a payload missing image_path")

    result = await quick_analyze(image_path)

    if not image_path or not os.path.exists(image_path):
        raise PermanentError(f"Image not found: {image_path}")

    # Detect color if item doesn't have it yet
    item_result = await db.execute(select(Item).where(Item.id == item_id))
    item = item_result.scalar_one_or_none()
    if item is None:
        raise PermanentError(f"Item {item_id} not found")

    item.cv_confidence = result.confidence
    item.cv_raw_output = {
        "phase_a": {
            "type": result.type,
            "has_graphic": result.has_graphic,
            "confidence": result.confidence,
            "needs_review": result.needs_review,
            "model_used": result.model_used,
            "processing_ms": result.processing_ms,
        }
    }

    # Set type from CV if item still has unknown type
    if item.type == ItemType.unknown or item.type is None:
        try:
            item.type = ItemType(result.type)
        except ValueError:
            item.type = ItemType.unknown

    # Fill color if still missing
    if not item.color:
        try:
            item.color = await detect_color(image_path)
        except Exception as e:
            logger.warning(f"Color detection failed for item {item_id}: {e}")

    await db.commit()

    return {
        "type": result.type,
        "confidence": result.confidence,
        "needs_review": result.needs_review,
        "processing_ms": result.processing_ms,
    }


async def _run_phase_b(db: AsyncSession, item_id: int, payload: dict) -> dict:
    image_path = payload.get("image_path")
    if not image_path:
        raise PermanentError("cv_phase_b payload missing image_path")

    if not os.path.exists(image_path):
        raise PermanentError(f"Image not found: {image_path}")

    result = await deep_analyze(image_path)

    item_result = await db.execute(select(Item).where(Item.id == item_id))
    item = item_result.scalar_one_or_none()
    if item is None:
        raise PermanentError(f"Item {item_id} not found")

    # Merge phase_b data into cv_raw_output
    raw = item.cv_raw_output or {}
    raw["phase_b"] = {
        "label": result.label,
        "graphic_description": result.graphic_description,
        "style_era": result.style_era,
        "visible_text": result.visible_text,
        "condition_notes": result.condition_notes,
        "resale_interest": result.resale_interest,
        "resale_reason": result.resale_reason,
        "model_used": result.model_used,
        "processing_ms": result.processing_ms,
    }
    item.cv_raw_output = raw
    item.cv_phase_b_complete = True

    await db.commit()
    return {"resale_interest": result.resale_interest, "processing_ms": result.processing_ms}


async def _run_fashion(db: AsyncSession, item_id: int, payload: dict) -> dict:
    image_path = payload.get("image_path")
    if not image_path:
        raise PermanentError("fashion_attributes payload missing image_path")

    if not os.path.exists(image_path):
        raise PermanentError(f"Image not found: {image_path}")

    result = await analyze_fashion(image_path)

    item_result = await db.execute(select(Item).where(Item.id == item_id))
    item = item_result.scalar_one_or_none()
    if item is None:
        raise PermanentError(f"Item {item_id} not found")

    # fashion_attributes failure returns null fields — still store it
    item.fashion_attributes = {
        "fit": result.fit,
        "sleeve": result.sleeve,
        "neckline": result.neckline,
        "fabric_weight": result.fabric_weight,
        "style": result.style,
        "decade_style": result.decade_style,
        "confidence_scores": result.confidence_scores,
        "model_used": result.model_used,
        "processing_ms": result.processing_ms,
    }

    await db.commit()
    return {"style": result.style, "decade_style": result.decade_style}


async def _run_print(item_id: int, payload: dict) -> dict:
    try:
        success = await send_label(item_id, payload)
        return {"printed": success}
    except (PrinterOfflineError, PrinterTimeoutError) as e:
        raise RetryableError(str(e))
    except PrinterError as e:
        raise PermanentError(str(e))


# ─── Main loop ────────────────────────────────────────────────────────────────

async def worker_loop() -> None:
    logger.info("Queue worker started")
    while True:
        try:
            async with _SessionFactory() as db:
                job = await get_next_job(db)

            if job is None:
                await asyncio.sleep(2)
                continue

            logger.info(f"Processing job id={job.id} type={job.job_type} item_id={job.item_id} attempt={job.attempts}")

            try:
                async with _SessionFactory() as db:
                    result = await _dispatch(db, job)

                async with _SessionFactory() as db:
                    await complete_job(db, job.id, result)

                logger.info(f"Job {job.id} complete: {result}")

            except RetryableError as e:
                logger.warning(f"Job {job.id} retryable failure: {e}")
                async with _SessionFactory() as db:
                    await fail_job(db, job.id, str(e), permanent=False)

            except PermanentError as e:
                logger.error(f"Job {job.id} permanent failure: {e}")
                async with _SessionFactory() as db:
                    await fail_job(db, job.id, str(e), permanent=True)

            except Exception as e:
                logger.exception(f"Job {job.id} unexpected error: {e}")
                async with _SessionFactory() as db:
                    await fail_job(db, job.id, f"Unexpected: {e}", permanent=False)

        except Exception as e:
            logger.exception(f"Worker loop error: {e}")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(worker_loop())
