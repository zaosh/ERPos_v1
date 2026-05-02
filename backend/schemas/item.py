from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, field_validator
from models.item import ItemCategory, ItemType, ItemCondition, ItemStatus


class CaptureResponse(BaseModel):
    """Capture now returns only temp_image_id and color (K-means, fast).
    Type analysis happens via cv_phase_a job after item creation."""
    temp_image_id: str
    color: Optional[str] = None


class ItemCreate(BaseModel):
    temp_image_id: str
    category: ItemCategory
    color: Optional[str] = None
    secondary_color: Optional[str] = None
    type: ItemType = ItemType.unknown  # Worker fills this via cv_phase_a
    label: Optional[str] = None
    size: Optional[str] = None
    condition: ItemCondition
    price: Decimal
    notes: Optional[str] = None

    @field_validator("price")
    @classmethod
    def price_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Price must be positive")
        return round(v, 2)


class ItemResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    barcode: str
    category: ItemCategory
    color: Optional[str]
    secondary_color: Optional[str]
    type: ItemType
    label: Optional[str]
    size: Optional[str]
    condition: ItemCondition
    price: Decimal
    cv_confidence: Optional[float]
    cv_raw_output: Optional[dict]
    image_path: Optional[str]
    image_thumb_path: Optional[str]
    image_url: Optional[str] = None
    image_thumb_url: Optional[str] = None
    status: ItemStatus
    notes: Optional[str]
    created_by: Optional[int]
    created_at: datetime
    updated_at: datetime
    sold_at: Optional[datetime]


class ItemCreateResponse(ItemResponse):
    cv_job_id: Optional[int] = None
    print_job_id: Optional[int] = None


class ItemUpdate(BaseModel):
    category: Optional[ItemCategory] = None
    color: Optional[str] = None
    secondary_color: Optional[str] = None
    type: Optional[ItemType] = None
    label: Optional[str] = None
    size: Optional[str] = None
    condition: Optional[ItemCondition] = None
    price: Optional[Decimal] = None
    notes: Optional[str] = None
    status: Optional[ItemStatus] = None

    @field_validator("price")
    @classmethod
    def price_positive(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v <= 0:
            raise ValueError("Price must be positive")
        return v


class ItemListResponse(BaseModel):
    items: list[ItemResponse]
    total: int
    limit: int
    offset: int
