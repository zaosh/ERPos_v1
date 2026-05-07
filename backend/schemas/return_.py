from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, field_validator
from models.return_ import RefundMethod, ReturnStatus


class ReturnCreate(BaseModel):
    sale_ref: str
    item_ids: list[int]
    return_reason: str
    refund_method: RefundMethod
    refund_amount: Optional[Decimal] = None
    notes: Optional[str] = None
    resellable: bool = True

    @field_validator("item_ids")
    @classmethod
    def items_not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("At least one item required for return")
        return v

    @field_validator("return_reason")
    @classmethod
    def reason_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Return reason cannot be empty")
        return v

    @field_validator("refund_amount")
    @classmethod
    def refund_non_negative(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and v < 0:
            raise ValueError("Refund amount cannot be negative")
        return v


class ReturnItemResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    item_id: int
    original_price: Decimal
    refund_price: Decimal


class ReturnResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    return_ref: str
    original_sale_id: int
    customer_id: Optional[int]
    return_reason: str
    processed_by: int
    refund_amount: Decimal
    refund_method: RefundMethod
    status: ReturnStatus
    notes: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]
    items: list[ReturnItemResponse] = []
