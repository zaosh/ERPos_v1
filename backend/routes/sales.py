import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user, require_admin, require_staff
from middleware.audit import write_audit_log
from models.item import Item, ItemStatus
from models.sale import Sale, SaleItem
from models.user import User
from schemas.sale import SaleCreate, SaleListResponse, SaleResponse, VoidRequest

logger = logging.getLogger(__name__)
router = APIRouter()


def _sale_ref(sale_id_hint: int) -> str:
    now = datetime.now(timezone.utc)
    return f"SALE-{now.strftime('%Y%m%d')}-{sale_id_hint:03d}"


def _sale_to_response(sale: Sale, sale_items: list[SaleItem]) -> dict:
    return {
        "id": sale.id,
        "sale_ref": sale.sale_ref,
        "total_amount": sale.total_amount,
        "discount": sale.discount,
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

    total = sum(found_items[bc].price for bc in barcodes)
    final_total = max(total - body.discount, 0)

    sale = Sale(
        sale_ref="SALE-PENDING",
        total_amount=final_total,
        discount=body.discount,
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
            "total_amount": str(final_total),
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
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import func
    count_result = await db.execute(select(func.count(Sale.id)))
    total = count_result.scalar_one()

    result = await db.execute(select(Sale).order_by(Sale.created_at.desc()).offset(offset).limit(limit))
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
