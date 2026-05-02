import enum
from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import DateTime, String, Text, Float, Numeric, ForeignKey, Index, Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from models.base import Base, TimestampMixin


class ItemCategory(str, enum.Enum):
    tshirt = "tshirt"
    pants = "pants"
    jacket = "jacket"
    dress = "dress"
    skirt = "skirt"
    shorts = "shorts"
    sweater = "sweater"
    hoodie = "hoodie"
    other = "other"


class ItemType(str, enum.Enum):
    plain = "plain"
    graphic = "graphic"
    patterned = "patterned"
    striped = "striped"
    band = "band"
    anime = "anime"
    sports = "sports"
    vintage_graphic = "vintage_graphic"
    holiday = "holiday"
    branded = "branded"
    statement = "statement"
    unknown = "unknown"


class ItemCondition(str, enum.Enum):
    excellent = "excellent"
    good = "good"
    fair = "fair"
    worn = "worn"


class ItemStatus(str, enum.Enum):
    in_stock = "in_stock"
    sold = "sold"
    reserved = "reserved"
    archived = "archived"


class Item(Base, TimestampMixin):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    barcode: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    category: Mapped[ItemCategory] = mapped_column(SAEnum(ItemCategory, name="item_category"), nullable=False)
    color: Mapped[Optional[str]] = mapped_column(String(30))
    secondary_color: Mapped[Optional[str]] = mapped_column(String(30))
    type: Mapped[ItemType] = mapped_column(SAEnum(ItemType, name="item_type"), nullable=False)
    label: Mapped[Optional[str]] = mapped_column(String(100))
    size: Mapped[Optional[str]] = mapped_column(String(10))
    condition: Mapped[ItemCondition] = mapped_column(SAEnum(ItemCondition, name="item_condition"), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    cv_confidence: Mapped[Optional[float]] = mapped_column(Float)
    cv_raw_output: Mapped[Optional[dict]] = mapped_column(JSONB)
    cv_color_correct: Mapped[Optional[bool]] = mapped_column()
    cv_type_correct: Mapped[Optional[bool]] = mapped_column()
    cv_phase_b_complete: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    fashion_attributes: Mapped[Optional[dict]] = mapped_column(JSONB)
    image_path: Mapped[Optional[str]] = mapped_column(String(500))
    image_thumb_path: Mapped[Optional[str]] = mapped_column(String(500))
    status: Mapped[ItemStatus] = mapped_column(
        SAEnum(ItemStatus, name="item_status"), nullable=False, default=ItemStatus.in_stock
    )
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))
    sold_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("idx_items_status", "status"),
        Index("idx_items_category_color", "category", "color"),
        Index("idx_items_label", "label"),
        Index("idx_items_created_at", "created_at"),
        Index("idx_items_sold_at", "sold_at"),
    )

    def __repr__(self) -> str:
        return f"<Item id={self.id} barcode={self.barcode} status={self.status}>"
