import enum
from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import BigInteger, DateTime, String, Text, Numeric, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from models.base import Base, TimestampMixin


class PaymentType(str, enum.Enum):
    cash = "cash"
    card = "card"
    other = "other"


class Sale(Base, TimestampMixin):
    __tablename__ = "sales"

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_ref: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    receipt_number: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    customer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("customers.id"))
    subtotal: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0"), server_default="0")
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"), server_default="0")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    payment_type: Mapped[PaymentType] = mapped_column(SAEnum(PaymentType, name="payment_type"), nullable=False)
    cashier_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    voided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    voided_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    exchange_fee_total: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=Decimal("0"), server_default="0"
    )

    @property
    def discount(self) -> Decimal:
        """Backward-compat alias for discount_amount."""
        return self.discount_amount

    def __repr__(self) -> str:
        return f"<Sale id={self.id} ref={self.sale_ref} total={self.total_amount}>"


class SaleItem(Base):
    __tablename__ = "sale_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id", ondelete="RESTRICT"), nullable=False)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="RESTRICT"), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    def __repr__(self) -> str:
        return f"<SaleItem sale_id={self.sale_id} item_id={self.item_id} price={self.price}>"
