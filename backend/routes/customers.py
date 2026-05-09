import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import require_admin, require_staff
from middleware.audit import write_audit_log
from models.customer import Customer
from models.return_ import Return
from models.sale import Sale, SaleItem
from models.user import User
from services import settings_service
from services.image_service import get_image_url
from schemas.customer import (
    CustomerCreate,
    CustomerUpdate,
    CustomerResponse,
    GdprEraseRequest,
    MaskedCustomerResponse,
)
from schemas.return_ import ReturnResponse, ReturnItemResponse
from services.customer_service import generate_customer_uid
from services.phone_service import (
    normalize_and_validate,
    get_default_region,
    get_display_format,
    get_masked_format,
    is_mobile,
)

logger = logging.getLogger(__name__)
router = APIRouter()


async def _lookup_customer(db: AsyncSession, customer_uid: str) -> Customer:
    result = await db.execute(
        select(Customer).where(Customer.customer_uid == customer_uid)
    )
    customer = result.scalar_one_or_none()
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


async def _validate_phone(raw: str, db: AsyncSession) -> str:
    """Normalize, validate, and assert mobile. Returns E.164. Raises HTTPException on failure."""
    region = await get_default_region(db)
    try:
        e164 = normalize_and_validate(raw, region)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not is_mobile(e164):
        raise HTTPException(status_code=422, detail="Please enter a mobile number")
    return e164


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_customer(
    body: CustomerCreate,
    request: Request,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    e164 = await _validate_phone(body.phone, db)

    # Check if phone already exists — return customer_uid on collision
    existing = await db.scalar(
        select(Customer.customer_uid).where(
            Customer.phone == e164,
            Customer.gdpr_erased_at.is_(None),
        )
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail={"message": "customer found", "customer_uid": existing},
        )

    customer_uid = await generate_customer_uid(db)
    customer = Customer(
        customer_uid=customer_uid,
        first_name=body.first_name,
        last_name=body.last_name,
        phone=e164,
        email=body.email,
        notes=body.notes,
    )
    db.add(customer)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        existing = await db.scalar(
            select(Customer.customer_uid).where(Customer.phone == e164)
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail={"message": "customer found", "customer_uid": existing},
            )
        raise

    await write_audit_log(
        db,
        table_name="customers",
        record_id=customer.id,
        action="INSERT",
        user_id=current_user.id,
        new_values={
            "customer_uid": customer_uid,
            "phone": e164,  # audit.py will mask this
            "first_name": body.first_name,
        },
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(customer)
    return CustomerResponse.model_validate(customer)


@router.get("/lookup")
async def lookup_customer(
    phone: str,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    if len(phone.strip()) < 4:
        raise HTTPException(status_code=422, detail="Phone must be at least 4 characters")

    # Try full normalization; fall back to suffix search for partial inputs
    region = await get_default_region(db)
    normalized: Optional[str] = None
    try:
        normalized = normalize_and_validate(phone, region)
    except ValueError:
        pass

    if normalized:
        result = await db.execute(
            select(Customer).where(
                Customer.phone == normalized,
                Customer.gdpr_erased_at.is_(None),
                Customer.is_active.is_(True),
            )
        )
        customer = result.scalar_one_or_none()
    else:
        digits = "".join(c for c in phone if c.isdigit())
        result = await db.execute(
            select(Customer).where(
                Customer.phone.like(f"%{digits}"),
                Customer.gdpr_erased_at.is_(None),
                Customer.is_active.is_(True),
            )
        )
        customer = result.scalar_one_or_none()

    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")

    total_purchases = await db.scalar(
        select(func.count(Sale.id)).where(Sale.customer_id == customer.id)
    ) or 0

    last_sale = await db.scalar(
        select(func.max(Sale.created_at)).where(Sale.customer_id == customer.id)
    )

    stored_phone = customer.phone or ""
    return MaskedCustomerResponse(
        customer_uid=customer.customer_uid,
        first_name=customer.first_name or "",
        last_initial=(customer.last_name or " ")[0],
        phone_last4=stored_phone[-4:],
        phone_masked=get_masked_format(stored_phone) if stored_phone else "***",
        total_purchases=total_purchases,
        last_purchase_date=last_sale,
    )


@router.get("/{customer_uid}", response_model=CustomerResponse)
async def get_customer(
    customer_uid: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    customer = await _lookup_customer(db, customer_uid)
    if customer.gdpr_erased_at:
        raise HTTPException(status_code=410, detail="Customer record has been erased")
    response = CustomerResponse.model_validate(customer)
    if response.phone:
        response.phone = get_display_format(response.phone)
    return response


@router.patch("/{customer_uid}", response_model=CustomerResponse)
async def update_customer(
    customer_uid: str,
    body: CustomerUpdate,
    request: Request,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    customer = await _lookup_customer(db, customer_uid)

    update_data = body.model_dump(exclude_unset=True)
    old_values: dict = {}

    if "phone" in update_data and update_data["phone"]:
        e164 = await _validate_phone(update_data["phone"], db)
        update_data["phone"] = e164

        conflict = await db.scalar(
            select(Customer.id).where(
                Customer.phone == e164,
                Customer.id != customer.id,
                Customer.gdpr_erased_at.is_(None),
            )
        )
        if conflict:
            raise HTTPException(status_code=409, detail="Phone number already in use")
        old_values["phone"] = customer.phone  # audit.py will mask

    for field, value in update_data.items():
        setattr(customer, field, value)

    await write_audit_log(
        db,
        table_name="customers",
        record_id=customer.id,
        action="UPDATE",
        user_id=current_user.id,
        old_values=old_values or None,
        new_values={k: v for k, v in update_data.items() if k not in {"notes"}},
        ip_address=request.client.host if request.client else None,
    )

    await db.commit()
    await db.refresh(customer)
    response = CustomerResponse.model_validate(customer)
    if response.phone:
        response.phone = get_display_format(response.phone)
    return response


@router.post("/{customer_uid}/gdpr-erase", status_code=status.HTTP_200_OK)
async def gdpr_erase(
    customer_uid: str,
    body: GdprEraseRequest,
    request: Request,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    customer = await _lookup_customer(db, customer_uid)

    if customer.gdpr_erased_at:
        raise HTTPException(status_code=409, detail="Customer already erased")

    now = datetime.now(timezone.utc)
    customer.first_name = None
    customer.last_name = None
    customer.phone = None
    customer.email = None
    customer.notes = None
    customer.is_active = False
    customer.gdpr_erased_at = now

    await write_audit_log(
        db,
        table_name="customers",
        record_id=customer.id,
        action="UPDATE",
        user_id=current_user.id,
        new_values={"gdpr_erased_at": now.isoformat(), "customer_uid": customer_uid},
        ip_address=request.client.host if request.client else None,
    )

    await db.commit()
    return {"detail": "Customer record erased", "customer_uid": customer_uid}


@router.get("/{customer_uid}/eligible-bills")
async def get_eligible_bills(
    customer_uid: str,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """
    Staff-accessible. Returns all sales for this customer that contain at least one
    exchange-eligible item still within the exchange window. Used by the Exchange page.
    """
    from models.exchange import Exchange as ExchangeModel, ExchangeStatus
    from models.item import Item as ItemModel

    customer = await _lookup_customer(db, customer_uid)
    exchange_window_days = await settings_service.get_int(db, "exchange_window_days", default=30)
    now = datetime.now(timezone.utc)

    # Fetch all sales for this customer
    sales_result = await db.execute(
        select(Sale)
        .where(Sale.customer_id == customer.id, Sale.voided_at.is_(None))
        .order_by(Sale.created_at.desc())
        .limit(50)
    )
    sales = list(sales_result.scalars().all())

    out = []
    for sale in sales:
        # Check within exchange window
        days_old = (now - sale.created_at).days
        if days_old > exchange_window_days:
            continue

        # Fetch sale items with item details
        si_result = await db.execute(
            select(SaleItem, ItemModel)
            .join(ItemModel, SaleItem.item_id == ItemModel.id)
            .where(SaleItem.sale_id == sale.id)
        )
        rows = si_result.all()

        # Only include items that are exchange_eligible and not already exchanged
        eligible_items = []
        for si, item in rows:
            if not item.exchange_eligible:
                continue
            if item.status.value == "exchanged":
                continue
            # Check no completed exchange already exists for this item
            existing_ex = await db.scalar(
                select(ExchangeModel).where(
                    ExchangeModel.original_item_id == item.id,
                    ExchangeModel.status.in_([ExchangeStatus.pending, ExchangeStatus.completed]),
                )
            )
            if existing_ex:
                continue
            eligible_items.append({
                "item_id": item.id,
                "barcode": item.barcode,
                "label": item.label,
                "category": item.category.value,
                "color": item.color,
                "size": item.size,
                "condition": item.condition.value if item.condition else None,
                "price": str(si.price),
                "exchange_fee_paid": str(item.exchange_fee_paid) if item.exchange_fee_paid else "0",
                "image_url": get_image_url(item.image_path) if item.image_path else None,
                "image_thumb_url": get_image_url(item.image_thumb_path) if item.image_thumb_path else None,
            })

        if not eligible_items:
            continue

        out.append({
            "sale_ref": sale.sale_ref,
            "receipt_number": sale.receipt_number,
            "created_at": sale.created_at.isoformat(),
            "total_amount": str(sale.total_amount),
            "days_old": days_old,
            "window_expires_in_days": exchange_window_days - days_old,
            "eligible_items": eligible_items,
        })

    return out


@router.get("/{customer_uid}/exchanges")
async def get_customer_exchanges(
    customer_uid: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin only — all exchanges for a customer with status."""
    from models.exchange import Exchange
    from schemas.exchange import ExchangeResponse

    customer = await _lookup_customer(db, customer_uid)
    result = await db.execute(
        select(Exchange)
        .where(Exchange.customer_id == customer.id)
        .order_by(Exchange.created_at.desc())
    )
    exchanges = result.scalars().all()
    return [ExchangeResponse.model_validate(ex) for ex in exchanges]


@router.get("/{customer_uid}/returns")
async def get_customer_returns(
    customer_uid: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    customer = await _lookup_customer(db, customer_uid)

    from models.return_ import ReturnItem
    result = await db.execute(
        select(Return).where(Return.customer_id == customer.id).order_by(Return.created_at.desc())
    )
    returns = result.scalars().all()

    out = []
    for ret in returns:
        items_result = await db.execute(
            select(ReturnItem).where(ReturnItem.return_id == ret.id)
        )
        return_items = items_result.scalars().all()
        out.append(ReturnResponse(
            id=ret.id,
            return_ref=ret.return_ref,
            original_sale_id=ret.original_sale_id,
            customer_id=ret.customer_id,
            return_reason=ret.return_reason,
            processed_by=ret.processed_by,
            refund_amount=ret.refund_amount,
            refund_method=ret.refund_method,
            status=ret.status,
            notes=ret.notes,
            created_at=ret.created_at,
            completed_at=ret.completed_at,
            items=[ReturnItemResponse(
                id=ri.id, item_id=ri.item_id,
                original_price=ri.original_price,
                refund_price=ri.refund_price,
            ) for ri in return_items],
        ))
    return out
