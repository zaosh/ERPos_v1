from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, field_validator
from models.sale import PaymentType


class SaleItemInput(BaseModel):
    barcode: str
    exchange_eligible: bool = False  # Customer opts in at checkout; fee added to total


class SaleCreate(BaseModel):
    items: list[SaleItemInput]
    payment_type: PaymentType
    discount: Decimal = Decimal("0")
    customer_uid: Optional[str] = None
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
    exchange_eligible: bool = False
    exchange_fee_paid: Optional[Decimal] = None


class SaleResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    sale_ref: str
    receipt_number: str
    customer_id: Optional[int]
    subtotal: Decimal
    discount_amount: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    payment_type: PaymentType
    cashier_id: Optional[int]
    notes: Optional[str]
    items: list[SaleItemResponse] = []
    exchange_fee_total: Decimal = Decimal("0")
    created_at: datetime
    voided_at: Optional[datetime]


class ReceiptLineItem(BaseModel):
    item_id: int
    barcode: str
    label: Optional[str]
    category: str
    color: Optional[str]
    size: Optional[str]
    condition: Optional[str] = None
    price: Decimal
    returned: bool = False
    exchange_eligible: bool = False
    exchange_fee_paid: Optional[Decimal] = None


class SaleReceiptResponse(BaseModel):
    sale_id: int
    store_name: str
    receipt_footer: str
    sale_ref: str
    receipt_number: str
    created_at: datetime
    cashier_first_name: str
    customer_display: Optional[str]
    line_items: list[ReceiptLineItem]
    subtotal: Decimal
    discount_amount: Decimal
    tax_rate: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    payment_type: PaymentType
    return_window_days: int
    exchange_fee_total: Decimal = Decimal("0")
    exchange_window_days: int = 30


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
