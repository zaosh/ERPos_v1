"""
Queue service — manage job_queue table operations.

All functions take AsyncSession as first arg.
No FastAPI dependencies here — usable from both API routes and queue_worker.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.job_queue import JobQueue, JobStatus, JobType

logger = logging.getLogger(__name__)

# Sentinel for retryable/permanent errors used by queue_worker
class RetryableError(Exception):
    pass

class PermanentError(Exception):
    pass


async def enqueue(
    db: AsyncSession,
    job_type: JobType,
    payload: dict,
    item_id: Optional[int] = None,
    priority: int = 5,
    max_attempts: int = 3,
    created_by: Optional[int] = None,
) -> int:
    """Insert a pending job and return its id. Non-blocking."""
    job = JobQueue(
        job_type=job_type,
        status=JobStatus.pending,
        priority=priority,
        item_id=item_id,
        payload=payload,
        max_attempts=max_attempts,
        created_by=created_by,
        created_at=datetime.now(timezone.utc),
    )
    db.add(job)
    await db.flush()
    return job.id


async def get_next_job(db: AsyncSession) -> Optional[JobQueue]:
    """
    Atomically claim the highest-priority pending job.
    SKIP LOCKED ensures two workers never pick the same job.
    """
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(JobQueue)
        .where(
            JobQueue.status == JobStatus.pending,
            (JobQueue.next_retry_at.is_(None)) | (JobQueue.next_retry_at <= now),
        )
        .order_by(JobQueue.priority.asc(), JobQueue.created_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = result.scalar_one_or_none()
    if job is None:
        return None

    job.status = JobStatus.processing
    job.started_at = now
    job.attempts += 1
    await db.commit()
    return job


async def complete_job(db: AsyncSession, job_id: int, result: dict) -> None:
    j = await db.get(JobQueue, job_id)
    if j:
        j.status = JobStatus.complete
        j.completed_at = datetime.now(timezone.utc)
        j.result = result
        await db.commit()


async def fail_job(
    db: AsyncSession,
    job_id: int,
    error: str,
    permanent: bool = False,
) -> None:
    j = await db.get(JobQueue, job_id)
    if not j:
        return

    j.error_message = error

    if permanent or j.attempts >= j.max_attempts:
        j.status = JobStatus.failed
        j.completed_at = datetime.now(timezone.utc)
    else:
        backoff_s = min(2 ** j.attempts * 30, 3600)
        j.status = JobStatus.pending
        j.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=backoff_s)

    await db.commit()


async def retry_job(db: AsyncSession, job_id: int) -> bool:
    """Reset a failed job back to pending. Returns False if job not found or not failed."""
    j = await db.get(JobQueue, job_id)
    if not j or j.status not in (JobStatus.failed, JobStatus.cancelled):
        return False
    j.status = JobStatus.pending
    j.attempts = 0
    j.error_message = None
    j.next_retry_at = None
    j.started_at = None
    j.completed_at = None
    await db.commit()
    return True


async def get_job_status(db: AsyncSession, job_id: int) -> Optional[dict]:
    j = await db.get(JobQueue, job_id)
    if not j:
        return None
    return {
        "id": j.id,
        "job_type": j.job_type,
        "status": j.status,
        "attempts": j.attempts,
        "max_attempts": j.max_attempts,
        "result": j.result,
        "error_message": j.error_message,
        "created_at": j.created_at,
        "started_at": j.started_at,
        "completed_at": j.completed_at,
    }


async def get_item_jobs(db: AsyncSession, item_id: int) -> list[dict]:
    result = await db.execute(
        select(JobQueue)
        .where(JobQueue.item_id == item_id)
        .order_by(JobQueue.created_at.asc())
    )
    jobs = result.scalars().all()
    return [
        {
            "id": j.id,
            "job_type": j.job_type,
            "status": j.status,
            "attempts": j.attempts,
            "error_message": j.error_message,
            "created_at": j.created_at,
            "completed_at": j.completed_at,
        }
        for j in jobs
    ]


async def get_queue_summary(db: AsyncSession) -> dict:
    """Counts grouped by (status, job_type) for the monitoring panel."""
    result = await db.execute(
        select(JobQueue.job_type, JobQueue.status, func.count().label("cnt"))
        .group_by(JobQueue.job_type, JobQueue.status)
    )
    rows = result.all()

    pending_by_type: dict[str, int] = {}
    failed_count = 0
    pending_count = 0

    for row in rows:
        if row.status == JobStatus.pending:
            pending_by_type[row.job_type] = pending_by_type.get(row.job_type, 0) + row.cnt
            pending_count += row.cnt
        elif row.status == JobStatus.failed:
            failed_count += row.cnt

    return {
        "pending_count": pending_count,
        "failed_count": failed_count,
        "pending_by_type": pending_by_type,
    }


async def get_failed_jobs(db: AsyncSession, limit: int = 50) -> list[dict]:
    result = await db.execute(
        select(JobQueue)
        .where(JobQueue.status == JobStatus.failed)
        .order_by(JobQueue.created_at.desc())
        .limit(limit)
    )
    jobs = result.scalars().all()
    return [
        {
            "id": j.id,
            "job_type": j.job_type,
            "item_id": j.item_id,
            "attempts": j.attempts,
            "max_attempts": j.max_attempts,
            "error_message": j.error_message,
            "payload": j.payload,
            "created_at": j.created_at,
            "completed_at": j.completed_at,
        }
        for j in jobs
    ]


async def get_recent_completed(db: AsyncSession, limit: int = 5) -> list[dict]:
    result = await db.execute(
        select(JobQueue)
        .where(JobQueue.status == JobStatus.complete)
        .order_by(JobQueue.completed_at.desc())
        .limit(limit)
    )
    jobs = result.scalars().all()
    return [
        {
            "id": j.id,
            "job_type": j.job_type,
            "item_id": j.item_id,
            "completed_at": j.completed_at,
        }
        for j in jobs
    ]
