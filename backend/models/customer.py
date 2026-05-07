import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column
from models.base import Base, TimestampMixin


class Customer(Base, TimestampMixin):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    customer_uid: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    first_name: Mapped[Optional[str]] = mapped_column(String(80))
    last_name: Mapped[Optional[str]] = mapped_column(String(80))
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    email: Mapped[Optional[str]] = mapped_column(String(255))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    gdpr_erased_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    tenant_id: Mapped[Optional[int]] = mapped_column(Integer, default=1, server_default="1")

    __table_args__ = (
        Index("idx_customers_last_name", "last_name"),
        Index("idx_customers_created_at", "created_at"),
        Index("idx_customers_tenant_id", "tenant_id"),
    )

    def __repr__(self) -> str:
        return f"<Customer id={self.id} uid={self.customer_uid}>"
