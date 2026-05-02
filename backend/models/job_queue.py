import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import BigInteger, DateTime, Integer, Text, ForeignKey, Index, Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from models.base import Base


class JobType(str, enum.Enum):
    cv_phase_a = "cv_phase_a"
    cv_phase_b = "cv_phase_b"
    fashion_attributes = "fashion_attributes"
    print_label = "print_label"
    print_retry = "print_retry"


class JobStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    complete = "complete"
    failed = "failed"
    cancelled = "cancelled"


class JobQueue(Base):
    __tablename__ = "job_queue"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_type: Mapped[JobType] = mapped_column(SAEnum(JobType, name="job_type_enum"), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        SAEnum(JobStatus, name="job_status_enum"), nullable=False, default=JobStatus.pending
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    item_id: Mapped[Optional[int]] = mapped_column(ForeignKey("items.id"))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    result: Mapped[Optional[dict]] = mapped_column(JSONB)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))

    __table_args__ = (
        Index("ix_job_queue_poll", "status", "priority", "created_at"),
        Index("ix_job_queue_item_id", "item_id"),
        Index("ix_job_queue_type_status", "job_type", "status"),
    )

    def __repr__(self) -> str:
        return f"<JobQueue id={self.id} type={self.job_type} status={self.status}>"
