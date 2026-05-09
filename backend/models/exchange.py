import enum
from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import (
    BigInteger, Boolean, DateTime, Integer, Numeric, String, Text,
    ForeignKey, Index, Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column
from models.base import Base


class ReturnedItemCondition(str, enum.Enum):
    excellent = "excellent"
    good = "good"
    fair = "fair"
    worn = "worn"
    damaged = "damaged"


class ExchangeStatus(str, enum.Enum):
    pending = "pending"
    completed = "completed"
    cancelled = "cancelled"


class BillEventType(str, enum.Enum):
    purchase = "purchase"
    exchange_initiated = "exchange_initiated"
    exchange_completed = "exchange_completed"
    return_initiated = "return_initiated"
    return_completed = "return_completed"
    item_added = "item_added"


class Exchange(Base):
    __tablename__ = "exchanges"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    exchange_ref: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    original_sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"), nullable=False)
    original_item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id"), nullable=False, unique=True
    )
    new_item_id: Mapped[Optional[int]] = mapped_column(ForeignKey("items.id"), unique=True)
    customer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("customers.id"), nullable=False)
    exchange_reason: Mapped[str] = mapped_column(Text, nullable=False)
    returned_item_condition: Mapped[ReturnedItemCondition] = mapped_column(
        SAEnum(ReturnedItemCondition, name="returned_item_condition_enum"), nullable=False
    )
    returned_item_image_confirmed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    exchange_fee: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[ExchangeStatus] = mapped_column(
        SAEnum(ExchangeStatus, name="exchange_status_enum"),
        nullable=False,
        default=ExchangeStatus.pending,
        server_default="pending",
    )
    processed_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    __table_args__ = (
        Index("idx_exchanges_sale", "original_sale_id"),
        Index("idx_exchanges_customer", "customer_id"),
        Index("idx_exchanges_status", "status"),
        Index("idx_exchanges_tenant_id", "tenant_id"),
    )

    def __repr__(self) -> str:
        return f"<Exchange id={self.id} ref={self.exchange_ref} status={self.status}>"


class BillHistory(Base):
    __tablename__ = "bill_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"), nullable=False)
    event_type: Mapped[BillEventType] = mapped_column(
        SAEnum(BillEventType, name="bill_event_type_enum"), nullable=False
    )
    item_id: Mapped[Optional[int]] = mapped_column(ForeignKey("items.id"))
    exchange_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("exchanges.id"))
    return_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("returns.id"))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    __table_args__ = (
        Index("idx_bill_history_sale", "sale_id"),
        Index("idx_bill_history_created_at", "created_at"),
        Index("idx_bill_history_tenant_id", "tenant_id"),
    )

    def __repr__(self) -> str:
        return f"<BillHistory id={self.id} sale_id={self.sale_id} event={self.event_type}>"
