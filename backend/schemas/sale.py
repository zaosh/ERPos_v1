from datetime import datetime
from decimal import Decimal
from typing import Optional, Literal
from pydantic import BaseModel, field_validator
from models.sale import PaymentType
from schemas.user import UserResponse


class SaleItemInput(BaseModel):
    barcode: str


class SaleCreate(BaseModel):
    items: list[SaleItemInput]
    payment_type: PaymentType
    discount: Decimal = Decimal("0")
    notes: Optional[str] = None

    @field_validator("items")
    @classmethod
    def items_not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("Sale must have at least one item")
        return v

    @field_validator("discount")
    @classmethod
    def discount_non_negative(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("Discount cannot be negative")
        return round(v, 2)


class SaleItemResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    item_id: int
    price: Decimal


class SaleResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    sale_ref: str
    total_amount: Decimal
    discount: Decimal
    payment_type: PaymentType
    cashier_id: Optional[int]
    notes: Optional[str]
    items: list[SaleItemResponse] = []
    created_at: datetime
    voided_at: Optional[datetime]


class VoidRequest(BaseModel):
    reason: str

    @field_validator("reason")
    @classmethod
    def reason_min_length(cls, v: str) -> str:
        if len(v.strip()) < 5:
            raise ValueError("Reason must be at least 5 characters")
        return v.strip()


class SaleListResponse(BaseModel):
    sales: list[SaleResponse]
    total: int
