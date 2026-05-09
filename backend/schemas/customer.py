from datetime import datetime
from typing import Optional
from pydantic import BaseModel, field_validator


class CustomerCreate(BaseModel):
    first_name: str
    last_name: str
    phone: str
    email: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("first_name", "last_name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name field cannot be empty")
        return v


class CustomerPhoneUpdate(BaseModel):
    phone: str
    reason: str

    @field_validator("reason")
    @classmethod
    def reason_min_length(cls, v: str) -> str:
        if len(v.strip()) < 5:
            raise ValueError("Reason must be at least 5 characters")
        return v.strip()


class CustomerUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None
    phone: Optional[str] = None


class GdprEraseRequest(BaseModel):
    confirm: str

    @field_validator("confirm")
    @classmethod
    def must_be_erase(cls, v: str) -> str:
        if v != "ERASE":
            raise ValueError('confirm field must be exactly "ERASE"')
        return v


class MaskedCustomerResponse(BaseModel):
    """Staff view — no full phone, no full last name."""
    customer_uid: str
    first_name: str
    last_initial: str
    phone_last4: str
    phone_masked: str
    total_purchases: int
    last_purchase_date: Optional[datetime]


class CustomerResponse(BaseModel):
    """Full record — admin only."""
    model_config = {"from_attributes": True}

    id: int
    customer_uid: str
    first_name: Optional[str]
    last_name: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    notes: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    gdpr_erased_at: Optional[datetime]
