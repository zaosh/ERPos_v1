from datetime import datetime
from typing import Optional
from sqlalchemy import DateTime, String, BigInteger, Integer, Index, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB, INET
from sqlalchemy.orm import Mapped, mapped_column
from models.base import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    table_name: Mapped[str] = mapped_column(String(50), nullable=False)
    record_id: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(10), nullable=False)
    old_values: Mapped[Optional[dict]] = mapped_column(JSONB)
    new_values: Mapped[Optional[dict]] = mapped_column(JSONB)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    ip_address: Mapped[Optional[str]] = mapped_column(INET)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_audit_table_record", "table_name", "record_id"),
    )

    def __repr__(self) -> str:
        return f"<AuditLog id={self.id} table={self.table_name} record={self.record_id} action={self.action}>"
