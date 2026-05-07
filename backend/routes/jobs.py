from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from dependencies import require_admin, require_staff
from models.user import User
from services.queue_service import (
    get_job_status,
    get_queue_summary,
    get_failed_jobs,
    get_recent_completed,
    retry_job,
)

router = APIRouter()


@router.get("/summary")
async def queue_summary(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Pending count by type, failed count. Admin only."""
    return await get_queue_summary(db)


@router.get("/failed")
async def failed_jobs(
    limit: int = 50,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Failed jobs with details for the monitoring panel. Admin only."""
    return await get_failed_jobs(db, limit=limit)


@router.get("/recent")
async def recent_jobs(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Last 5 completed jobs. Admin only."""
    return await get_recent_completed(db, limit=5)


@router.get("/config/public")
async def public_config(current_user: User = Depends(require_staff)):
    """Expose motion-detection thresholds to the frontend without a frontend rebuild."""
    return {
        "cv_stillness_threshold_ms": settings.CV_STILLNESS_THRESHOLD_MS,
        "cv_motion_threshold_pct": settings.CV_MOTION_THRESHOLD_PCT,
    }


@router.get("/{job_id}/status")
async def job_status(
    job_id: int,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """Poll a specific job's status. Any authenticated user can poll."""
    data = await get_job_status(db, job_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return data


@router.post("/{job_id}/retry")
async def retry_job_endpoint(
    job_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Reset a failed job to pending. Admin only."""
    ok = await retry_job(db, job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Job not found or not in failed state")
    return {"retried": True, "job_id": job_id}
