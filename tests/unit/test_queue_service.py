"""Unit tests for queue_service — backoff, SKIP LOCKED behavior, retry logic."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

import asyncio
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest
from models.job_queue import JobType, JobStatus
from services.queue_service import RetryableError, PermanentError


class TestEnqueue:
    @pytest.mark.asyncio
    async def test_enqueue_creates_pending_job(self, db_session, test_item):
        from services.queue_service import enqueue, get_job_status
        job_id = await enqueue(
            db_session,
            job_type=JobType.cv_phase_a,
            payload={"image_path": "/data/images/test.jpg"},
            item_id=test_item.id,
            priority=1,
            max_attempts=3,
        )
        await db_session.commit()

        status = await get_job_status(db_session, job_id)
        assert status is not None
        assert status["status"] == JobStatus.pending
        assert status["attempts"] == 0
        assert status["max_attempts"] == 3
        assert status["result"] is None


class TestFailJobBackoff:
    @pytest.mark.asyncio
    async def test_exponential_backoff_attempt_1(self, db_session, test_item):
        """After attempt 1: next_retry = 2^1 * 30 = 60s from now."""
        from services.queue_service import enqueue, fail_job, get_job_status
        job_id = await enqueue(db_session, JobType.print_label, {}, item_id=test_item.id, priority=1, max_attempts=5)
        await db_session.commit()

        from models.job_queue import JobQueue
        job = await db_session.get(JobQueue, job_id)
        job.attempts = 1
        await db_session.commit()

        before = datetime.now(timezone.utc)
        await fail_job(db_session, job_id, "timeout", permanent=False)

        status = await get_job_status(db_session, job_id)
        assert status["status"] == JobStatus.pending
        expected_backoff = timedelta(seconds=2**1 * 30)
        actual = status["error_message"]
        assert "timeout" in actual
        # next_retry_at should be approximately now + 60s
        retry_at = status  # we need the raw model
        from models.job_queue import JobQueue as JQ
        j = await db_session.get(JQ, job_id)
        diff = abs((j.next_retry_at - before).total_seconds() - 60)
        assert diff < 5  # within 5s tolerance

    @pytest.mark.asyncio
    async def test_exponential_backoff_capped_at_3600(self, db_session, test_item):
        """Backoff must not exceed 3600s."""
        from services.queue_service import enqueue, fail_job
        job_id = await enqueue(db_session, JobType.print_label, {}, item_id=test_item.id, priority=1, max_attempts=20)
        await db_session.commit()

        from models.job_queue import JobQueue
        job = await db_session.get(JobQueue, job_id)
        job.attempts = 10  # 2^10 * 30 = 30720 — should be capped at 3600
        await db_session.commit()

        before = datetime.now(timezone.utc)
        await fail_job(db_session, job_id, "long retry", permanent=False)

        job = await db_session.get(JobQueue, job_id)
        diff = (job.next_retry_at - before).total_seconds()
        assert diff <= 3601  # capped at 3600s + small tolerance

    @pytest.mark.asyncio
    async def test_permanent_failure_sets_failed_status(self, db_session, test_item):
        from services.queue_service import enqueue, fail_job, get_job_status
        job_id = await enqueue(db_session, JobType.cv_phase_b, {}, item_id=test_item.id, priority=5, max_attempts=3)
        await db_session.commit()

        await fail_job(db_session, job_id, "permanent error", permanent=True)

        status = await get_job_status(db_session, job_id)
        assert status["status"] == JobStatus.failed
        assert "permanent error" in status["error_message"]

    @pytest.mark.asyncio
    async def test_max_attempts_exceeded_sets_failed(self, db_session, test_item):
        from services.queue_service import enqueue, fail_job, get_job_status
        job_id = await enqueue(db_session, JobType.print_label, {}, item_id=test_item.id, priority=1, max_attempts=3)
        await db_session.commit()

        from models.job_queue import JobQueue
        job = await db_session.get(JobQueue, job_id)
        job.attempts = 3  # already at max
        await db_session.commit()

        await fail_job(db_session, job_id, "final attempt", permanent=False)

        status = await get_job_status(db_session, job_id)
        assert status["status"] == JobStatus.failed


class TestRetryJob:
    @pytest.mark.asyncio
    async def test_retry_resets_failed_job_to_pending(self, db_session, test_item):
        from services.queue_service import enqueue, fail_job, retry_job, get_job_status
        job_id = await enqueue(db_session, JobType.print_label, {}, item_id=test_item.id, priority=1, max_attempts=1)
        await db_session.commit()

        from models.job_queue import JobQueue
        job = await db_session.get(JobQueue, job_id)
        job.attempts = 1
        await db_session.commit()

        await fail_job(db_session, job_id, "printer error", permanent=True)
        assert (await get_job_status(db_session, job_id))["status"] == JobStatus.failed

        ok = await retry_job(db_session, job_id)
        assert ok is True

        status = await get_job_status(db_session, job_id)
        assert status["status"] == JobStatus.pending
        assert status["attempts"] == 0
        assert status["error_message"] is None

    @pytest.mark.asyncio
    async def test_retry_returns_false_for_non_failed_job(self, db_session, test_item):
        from services.queue_service import enqueue, retry_job
        job_id = await enqueue(db_session, JobType.cv_phase_a, {}, item_id=test_item.id)
        await db_session.commit()

        ok = await retry_job(db_session, job_id)
        assert ok is False


class TestGetNextJobSkipLocked:
    @pytest.mark.asyncio
    async def test_two_workers_get_different_jobs(self, test_engine, test_item):
        """
        SKIP LOCKED: two concurrent workers must never claim the same job.
        We simulate this by running two workers with separate sessions.
        """
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        from services.queue_service import enqueue, get_next_job

        session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

        # Enqueue two jobs
        async with session_factory() as db:
            job1_id = await enqueue(db, JobType.cv_phase_a, {}, item_id=test_item.id, priority=1)
            job2_id = await enqueue(db, JobType.cv_phase_b, {}, item_id=test_item.id, priority=1)
            await db.commit()

        # Two workers race to claim jobs
        async def worker(session):
            return await get_next_job(session)

        async with session_factory() as db1, session_factory() as db2:
            result1, result2 = await asyncio.gather(worker(db1), worker(db2))

        claimed_ids = set()
        if result1:
            claimed_ids.add(result1.id)
        if result2:
            claimed_ids.add(result2.id)

        # They should have gotten different jobs
        assert len(claimed_ids) == 2
        assert job1_id in claimed_ids
        assert job2_id in claimed_ids
