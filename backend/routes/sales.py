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
from schemas.exchange import BillHistoryEvent, LinkCustomer
from schemas.sale import (
    SaleCreate, SaleListResponse, SaleResponse, SaleReceiptResponse,
    ReceiptLineItem, VoidRequest,
)
from services import settings_service
from services.exchange_service import append_bill_history, get_bill_history
from services.receipt_service import next_receipt_number
from models.exchange import BillEventType

logger = logging.getLogger(__name__)
router = APIRouter()


def _sale_ref(sale_id_hint: int) -> str:
    now = datetime.now(timezone.utc)
    return f"SALE-{now.strftime('%Y%m%d')}-{sale_id_hint:03d}"


def _sale_to_response(sale: Sale, sale_items: list[SaleItem], items_map: dict | None = None) -> dict:
    line_items = []
    for si in sale_items:
        entry: dict = {"id": si.id, "item_id": si.item_id, "price": si.price}
        if items_map and si.item_id in items_map:
            it = items_map[si.item_id]
            entry["exchange_eligible"] = it.exchange_eligible
            entry["exchange_fee_paid"] = it.exchange_fee_paid
        line_items.append(entry)
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
        "exchange_fee_total": sale.exchange_fee_total,
        "payment_type": sale.payment_type,
        "cashier_id": sale.cashier_id,
        "notes": sale.notes,
        "items": line_items,
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

    # Exchange fee calculations
    exchange_eligible_barcodes = {i.barcode for i in body.items if i.exchange_eligible}
    exchange_fee_amount = Decimal("0")
    if exchange_eligible_barcodes:
        exchange_fee_amount = await settings_service.get_decimal(
            db, "exchange_fee_amount", default=Decimal("0")
        )
    exchange_fee_total = exchange_fee_amount * len(exchange_eligible_barcodes)

    # Billing calculations
    subtotal = sum(found_items[bc].price for bc in barcodes)
    discount_amount = min(body.discount, subtotal)
    tax_rate = await settings_service.get_decimal(db, "tax_rate", default=Decimal("0"))
    taxable = subtotal - discount_amount
    tax_amount = round(taxable * tax_rate, 2)
    total_amount = max(taxable + tax_amount + exchange_fee_total, Decimal("0"))

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
        exchange_fee_total=exchange_fee_total,
        payment_type=body.payment_type,
        cashier_id=current_user.id,
        notes=body.notes,
    )
    db.add(sale)
    await db.flush()

    sale.sale_ref = _sale_ref(sale.id)

    now = datetime.now(timezone.utc)
    sale_items = []
    for item_input in body.items:
        bc = item_input.barcode
        item = found_items[bc]
        item.status = ItemStatus.sold
        item.sold_at = now

        if item_input.exchange_eligible:
            item.exchange_eligible = True
            item.exchange_fee_paid = exchange_fee_amount

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

    # Append purchase event to bill history
    items_map = {item.id: item for item in found_items.values()}
    item_descriptions = ", ".join(
        f"{found_items[bc].barcode}"
        for bc in barcodes
    )
    await append_bill_history(
        db,
        sale_id=sale.id,
        event_type=BillEventType.purchase,
        description=f"Purchase: {len(barcodes)} item(s) — {item_descriptions[:200]}",
        created_by=current_user.id,
    )
    await db.commit()

    return _sale_to_response(sale, sale_items, items_map=items_map)


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

    # Which items were returned FROM THIS specific sale?
    # Must join through Return to scope by original_sale_id — an item resold after a
    # prior return must NOT show as returned on the new sale's receipt.
    from models.return_ import Return as ReturnModel
    sale_item_ids = [si.item_id for si in sale_item_rows]
    returned_ids: set[int] = set()
    if sale_item_ids:
        ri_result = await db.execute(
            select(ReturnItem.item_id)
            .join(ReturnModel, ReturnItem.return_id == ReturnModel.id)
            .where(
                ReturnItem.item_id.in_(sale_item_ids),
                ReturnModel.original_sale_id == sale.id,
            )
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
                exchange_eligible=item.exchange_eligible,
                exchange_fee_paid=item.exchange_fee_paid,
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
    exchange_window_days = await settings_service.get_int(db, "exchange_window_days", default=30)

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
        exchange_fee_total=sale.exchange_fee_total,
        exchange_window_days=exchange_window_days,
    )


@router.get("/{sale_ref}/history", response_model=list[BillHistoryEvent])
async def get_sale_history(
    sale_ref: str,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """Return the full event timeline for a sale in chronological order."""
    sale = await db.scalar(select(Sale).where(Sale.sale_ref == sale_ref))
    if sale is None:
        raise HTTPException(status_code=404, detail="Sale not found")
    events = await get_bill_history(sale.id, db)
    return events


@router.post("/{sale_ref}/link-customer")
async def link_customer_to_sale(
    sale_ref: str,
    body: LinkCustomer,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """
    Link an anonymous sale to a customer record.
    Required before initiating an exchange on an anonymous sale.
    Once linked, the customer_id cannot be changed.
    """
    sale = await db.scalar(
        select(Sale).where(Sale.sale_ref == sale_ref).with_for_update()
    )
    if sale is None:
        raise HTTPException(status_code=404, detail="Sale not found")
    if sale.customer_id is not None:
        raise HTTPException(
            status_code=409,
            detail="Sale is already linked to a customer — cannot re-link",
        )

    customer = await db.scalar(
        select(Customer).where(
            Customer.customer_uid == body.customer_uid,
            Customer.gdpr_erased_at.is_(None),
            Customer.is_active.is_(True),
        )
    )
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")

    sale.customer_id = customer.id
    await db.commit()
    return {"sale_ref": sale_ref, "customer_id": customer.id, "customer_uid": body.customer_uid}


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
