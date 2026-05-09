from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field, field_validator
from models.exchange import ExchangeStatus, ReturnedItemCondition, BillEventType


class ExchangeInitiate(BaseModel):
    sale_ref: str
    item_id: int
    customer_uid: str
    exchange_reason: str = Field(min_length=3, max_length=2000)
    returned_condition: ReturnedItemCondition
    image_confirmed: bool

    @field_validator("image_confirmed")
    @classmethod
    def must_confirm_image(cls, v: bool) -> bool:
        if not v:
            raise ValueError("image_confirmed must be true — staff must verify the item against the stored photo")
        return v


class ExchangeComplete(BaseModel):
    new_item_barcode: str


class LinkCustomer(BaseModel):
    customer_uid: str


class ExchangeResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    exchange_ref: str
    original_sale_id: int
    original_item_id: int
    new_item_id: Optional[int]
    customer_id: int
    exchange_reason: str
    returned_item_condition: ReturnedItemCondition
    returned_item_image_confirmed: bool
    exchange_fee: Decimal
    status: ExchangeStatus
    processed_by: int
    notes: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]


class BillHistoryEvent(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    sale_id: int
    event_type: BillEventType
    item_id: Optional[int]
    exchange_id: Optional[int]
    return_id: Optional[int]
    description: str
    created_by: int
    created_at: datetime
