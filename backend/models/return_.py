import enum
from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import (
    BigInteger, DateTime, Integer, Numeric, String, Text, ForeignKey, Index,
    UniqueConstraint, Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column
from models.base import Base, TimestampMixin


class RefundMethod(str, enum.Enum):
    cash = "cash"
    card = "card"
    store_credit = "store_credit"


class ReturnStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    completed = "completed"
    rejected = "rejected"


class Return(Base, TimestampMixin):
    __tablename__ = "returns"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    return_ref: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    original_sale_id: Mapped[int] = mapped_column(
        ForeignKey("sales.id", ondelete="RESTRICT"), nullable=False
    )
    customer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("customers.id"))
    return_reason: Mapped[str] = mapped_column(Text, nullable=False)
    processed_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    refund_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    refund_method: Mapped[RefundMethod] = mapped_column(
        SAEnum(RefundMethod, name="refund_method_enum"), nullable=False
    )
    status: Mapped[ReturnStatus] = mapped_column(
        SAEnum(ReturnStatus, name="return_status_enum"),
        nullable=False,
        default=ReturnStatus.pending,
        server_default="pending",
    )
    notes: Mapped[Optional[str]] = mapped_column(Text)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    tenant_id: Mapped[Optional[int]] = mapped_column(Integer, default=1, server_default="1")

    __table_args__ = (
        Index("idx_returns_original_sale_id", "original_sale_id"),
        Index("idx_returns_customer_id", "customer_id"),
        Index("idx_returns_tenant_id", "tenant_id"),
    )

    def __repr__(self) -> str:
        return f"<Return id={self.id} ref={self.return_ref} status={self.status}>"


class ReturnItem(Base):
    __tablename__ = "return_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    return_id: Mapped[int] = mapped_column(
        ForeignKey("returns.id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="RESTRICT"), nullable=False
    )
    original_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    refund_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    tenant_id: Mapped[Optional[int]] = mapped_column(Integer, default=1, server_default="1")

    __table_args__ = (
        UniqueConstraint("item_id", name="uq_return_items_item_id"),
        Index("idx_return_items_return_id", "return_id"),
        Index("idx_return_items_tenant_id", "tenant_id"),
    )

    def __repr__(self) -> str:
        return f"<ReturnItem id={self.id} return_id={self.return_id} item_id={self.item_id}>"
