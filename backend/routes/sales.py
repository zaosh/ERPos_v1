import logging
from datetime import datetime, timezone
from decimal import Decimal

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user, require_admin, require_staff
from middleware.audit import write_audit_log
from models.customer import Customer
from models.item import Item, ItemStatus
from models.return_ import ReturnItem
from models.sale import Sale, SaleItem
from models.user import User
from schemas.sale import (
    SaleCreate, SaleListResponse, SaleResponse, SaleReceiptResponse,
    ReceiptLineItem, VoidRequest,
)
from services import settings_service
from services.receipt_service import next_receipt_number

logger = logging.getLogger(__name__)
router = APIRouter()


def _sale_ref(sale_id_hint: int) -> str:
    now = datetime.now(timezone.utc)
    return f"SALE-{now.strftime('%Y%m%d')}-{sale_id_hint:03d}"


def _sale_to_response(sale: Sale, sale_items: list[SaleItem]) -> dict:
    return {
        "id": sale.id,
        "sale_ref": sale.sale_ref,
        "receipt_number": sale.receipt_number,
        "customer_id": sale.customer_id,
        "subtotal": sale.subtotal,
        "discount_amount": sale.discount_amount,
        "tax_rate": sale.tax_rate,
        "tax_amount": sale.tax_amount,
        "total_amount": sale.total_amount,
        "payment_type": sale.payment_type,
        "cashier_id": sale.cashier_id,
        "notes": sale.notes,
        "items": [{"id": si.id, "item_id": si.item_id, "price": si.price} for si in sale_items],
        "created_at": sale.created_at,
        "voided_at": sale.voided_at,
    }


@router.post("/", response_model=SaleResponse, status_code=status.HTTP_201_CREATED)
async def create_sale(
    body: SaleCreate,
    request: Request,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    barcodes = [i.barcode for i in body.items]

    result = await db.execute(
        select(Item).where(Item.barcode.in_(barcodes), Item.deleted_at.is_(None)).with_for_update()
    )
    found_items = {item.barcode: item for item in result.scalars().all()}

    for bc in barcodes:
        if bc not in found_items:
            raise HTTPException(status_code=404, detail=f"Item with barcode {bc} not found")
        if found_items[bc].status != ItemStatus.in_stock:
            raise HTTPException(
                status_code=409,
                detail=f"Item {bc} is not available (status: {found_items[bc].status.value})",
            )

    # Customer lookup (optional)
    customer_id: int | None = None
    if body.customer_uid:
        customer = await db.scalar(
            select(Customer).where(
                Customer.customer_uid == body.customer_uid,
                Customer.gdpr_erased_at.is_(None),
                Customer.is_active.is_(True),
            )
        )
        if customer is None:
            raise HTTPException(status_code=404, detail="Customer not found")
        customer_id = customer.id

    # Billing calculations
    subtotal = sum(found_items[bc].price for bc in barcodes)
    discount_amount = min(body.discount, subtotal)
    tax_rate = await settings_service.get_decimal(db, "tax_rate", default=Decimal("0"))
    taxable = subtotal - discount_amount
    tax_amount = round(taxable * tax_rate, 2)
    total_amount = max(taxable + tax_amount, Decimal("0"))

    # Generate receipt_number inside this transaction (advisory-lock protected)
    receipt_number = await next_receipt_number(db)

    sale = Sale(
        sale_ref="SALE-PENDING",
        receipt_number=receipt_number,
        customer_id=customer_id,
        subtotal=subtotal,
        discount_amount=discount_amount,
        tax_rate=tax_rate,
        tax_amount=tax_amount,
        total_amount=total_amount,
        payment_type=body.payment_type,
        cashier_id=current_user.id,
        notes=body.notes,
    )
    db.add(sale)
    await db.flush()

    sale.sale_ref = _sale_ref(sale.id)

    now = datetime.now(timezone.utc)
    sale_items = []
    for bc in barcodes:
        item = found_items[bc]
        item.status = ItemStatus.sold
        item.sold_at = now

        si = SaleItem(sale_id=sale.id, item_id=item.id, price=item.price)
        db.add(si)
        sale_items.append(si)

    await write_audit_log(
        db,
        table_name="sales",
        record_id=sale.id,
        action="INSERT",
        user_id=current_user.id,
        new_values={
            "sale_ref": sale.sale_ref,
            "receipt_number": receipt_number,
            "total_amount": str(total_amount),
            "customer_id": customer_id,
            "item_count": len(barcodes),
        },
        ip_address=request.client.host if request.client else None,
    )

    await db.commit()
    await db.refresh(sale)
    return _sale_to_response(sale, sale_items)


@router.get("/{sale_id}", response_model=SaleResponse)
async def get_sale(
    sale_id: int,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Sale).where(Sale.id == sale_id))
    sale = result.scalar_one_or_none()
    if sale is None:
        raise HTTPException(status_code=404, detail="Sale not found")

    items_result = await db.execute(select(SaleItem).where(SaleItem.sale_id == sale_id))
    sale_items = items_result.scalars().all()

    return _sale_to_response(sale, list(sale_items))


@router.get("/", response_model=SaleListResponse)
async def list_sales(
    limit: int = 50,
    offset: int = 0,
    sale_ref: Optional[str] = None,
    receipt_number: Optional[str] = None,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import func
    base_q = select(Sale)
    if sale_ref:
        base_q = base_q.where(Sale.sale_ref == sale_ref)
    if receipt_number:
        base_q = base_q.where(Sale.receipt_number == receipt_number)

    count_result = await db.execute(select(func.count()).select_from(base_q.subquery()))
    total = count_result.scalar_one()

    result = await db.execute(base_q.order_by(Sale.created_at.desc()).offset(offset).limit(limit))
    sales = result.scalars().all()

    sale_responses = []
    for sale in sales:
        items_result = await db.execute(select(SaleItem).where(SaleItem.sale_id == sale.id))
        sale_items = items_result.scalars().all()
        sale_responses.append(SaleResponse.model_validate(_sale_to_response(sale, list(sale_items))))

    return SaleListResponse(sales=sale_responses, total=total)


@router.post("/{sale_id}/void")
async def void_sale(
    sale_id: int,
    body: VoidRequest,
    request: Request,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Sale).where(Sale.id == sale_id).with_for_update())
    sale = result.scalar_one_or_none()
    if sale is None:
        raise HTTPException(status_code=404, detail="Sale not found")
    if sale.voided_at is not None:
        raise HTTPException(status_code=409, detail="Sale already voided")

    now = datetime.now(timezone.utc)
    sale.voided_at = now
    sale.voided_by = current_user.id

    items_result = await db.execute(select(SaleItem).where(SaleItem.sale_id == sale_id))
    sale_items = items_result.scalars().all()

    for si in sale_items:
        item_result = await db.execute(select(Item).where(Item.id == si.item_id).with_for_update())
        item = item_result.scalar_one_or_none()
        if item:
            item.status = ItemStatus.in_stock
            item.sold_at = None

    await write_audit_log(
        db,
        table_name="sales",
        record_id=sale.id,
        action="UPDATE",
        user_id=current_user.id,
        old_values={"voided_at": None},
        new_values={"voided_at": now.isoformat(), "reason": body.reason},
        ip_address=request.client.host if request.client else None,
    )

    await db.commit()
    return {"detail": "Sale voided", "sale_id": sale_id}


@router.get("/by-receipt/{receipt_number}", response_model=SaleReceiptResponse)
async def get_receipt_by_receipt_number(
    receipt_number: str,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    sale = await db.scalar(select(Sale).where(Sale.receipt_number == receipt_number))
    if sale is None:
        raise HTTPException(status_code=404, detail="Sale not found")
    return await get_receipt(sale.sale_ref, current_user, db)


@router.get("/{sale_ref}/receipt", response_model=SaleReceiptResponse)
async def get_receipt(
    sale_ref: str,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    sale_result = await db.execute(select(Sale).where(Sale.sale_ref == sale_ref))
    sale = sale_result.scalar_one_or_none()
    if sale is None:
        raise HTTPException(status_code=404, detail="Sale not found")

    items_result = await db.execute(select(SaleItem).where(SaleItem.sale_id == sale.id))
    sale_item_rows = items_result.scalars().all()

    # Which items from this sale have been returned?
    sale_item_ids = [si.item_id for si in sale_item_rows]
    returned_ids: set[int] = set()
    if sale_item_ids:
        ri_result = await db.execute(
            select(ReturnItem.item_id).where(ReturnItem.item_id.in_(sale_item_ids))
        )
        returned_ids = set(ri_result.scalars().all())

    line_items = []
    for si in sale_item_rows:
        item_result = await db.execute(select(Item).where(Item.id == si.item_id))
        item = item_result.scalar_one_or_none()
        if item:
            line_items.append(ReceiptLineItem(
                item_id=item.id,
                barcode=item.barcode,
                label=item.label,
                category=item.category.value,
                color=item.color,
                size=item.size,
                condition=item.condition.value if item.condition else None,
                price=si.price,
                returned=item.id in returned_ids,
            ))

    # Cashier first name
    cashier_name = "Staff"
    if sale.cashier_id:
        cashier_result = await db.execute(select(User).where(User.id == sale.cashier_id))
        cashier = cashier_result.scalar_one_or_none()
        if cashier:
            cashier_name = cashier.username

    # Customer display (first + last initial only)
    customer_display: str | None = None
    if sale.customer_id:
        cust_result = await db.execute(select(Customer).where(Customer.id == sale.customer_id))
        cust = cust_result.scalar_one_or_none()
        if cust and cust.first_name and not cust.gdpr_erased_at:
            last_initial = (cust.last_name or " ")[0]
            customer_display = f"{cust.first_name} {last_initial}."

    store_name = await settings_service.get(db, "store_name") or "qstar"
    receipt_footer = await settings_service.get(db, "receipt_footer") or "Thank you for shopping with us"
    return_window_days = await settings_service.get_int(db, "return_window_days", default=14)

    return SaleReceiptResponse(
        sale_id=sale.id,
        store_name=store_name,
        receipt_footer=receipt_footer,
        sale_ref=sale.sale_ref,
        receipt_number=sale.receipt_number,
        created_at=sale.created_at,
        cashier_first_name=cashier_name,
        customer_display=customer_display,
        line_items=line_items,
        subtotal=sale.subtotal,
        discount_amount=sale.discount_amount,
        tax_rate=sale.tax_rate,
        tax_amount=sale.tax_amount,
        total_amount=sale.total_amount,
        payment_type=sale.payment_type,
        return_window_days=return_window_days,
    )


@router.post("/{sale_ref}/email-receipt")
async def email_receipt(
    sale_ref: str,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """Stub — email service not yet configured. Logs the intent."""
    sale_result = await db.execute(select(Sale).where(Sale.sale_ref == sale_ref))
    sale = sale_result.scalar_one_or_none()
    if sale is None:
        raise HTTPException(status_code=404, detail="Sale not found")
    logger.info(f"Email receipt requested for sale {sale_ref} (not yet implemented)")
    return {"detail": "Email receipt queued", "sale_ref": sale_ref}
