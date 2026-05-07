import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import require_admin
from middleware.audit import write_audit_log
from models.item import Item, ItemStatus
from models.return_ import Return, ReturnItem, ReturnStatus
from models.sale import Sale, SaleItem
from models.user import User
from schemas.return_ import ReturnCreate, ReturnItemResponse, ReturnResponse
from services.receipt_service import next_return_ref
from services import settings_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/", response_model=ReturnResponse, status_code=status.HTTP_201_CREATED)
async def create_return(
    body: ReturnCreate,
    request: Request,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    # Validate sale exists and is not voided
    sale_result = await db.execute(
        select(Sale).where(Sale.sale_ref == body.sale_ref).with_for_update()
    )
    sale = sale_result.scalar_one_or_none()
    if sale is None:
        raise HTTPException(status_code=404, detail="Sale not found")
    if sale.voided_at is not None:
        raise HTTPException(status_code=422, detail="Cannot return items from a voided sale")

    # Check return window
    return_window_days = await settings_service.get_int(db, "return_window_days", default=14)
    now = datetime.now(timezone.utc)
    sale_age_days = (now - sale.created_at).days
    if sale_age_days > return_window_days:
        raise HTTPException(
            status_code=422,
            detail=f"Sale is outside the {return_window_days}-day return window ({sale_age_days} days old)",
        )

    # Load sale items and validate all requested items belong to this sale
    sale_items_result = await db.execute(
        select(SaleItem).where(SaleItem.sale_id == sale.id)
    )
    sale_items_map = {si.item_id: si for si in sale_items_result.scalars().all()}

    for item_id in body.item_ids:
        if item_id not in sale_items_map:
            raise HTTPException(
                status_code=400,
                detail=f"Item {item_id} was not part of sale {body.sale_ref}",
            )

    # Load items with lock
    items_result = await db.execute(
        select(Item)
        .where(Item.id.in_(body.item_ids))
        .with_for_update()
    )
    items = {item.id: item for item in items_result.scalars().all()}

    # Calculate refund amount if not provided
    if body.refund_amount is not None:
        refund_amount = body.refund_amount
    else:
        refund_amount = sum(sale_items_map[iid].price for iid in body.item_ids)

    return_ref = await next_return_ref(db)

    ret = Return(
        return_ref=return_ref,
        original_sale_id=sale.id,
        customer_id=sale.customer_id,
        return_reason=body.return_reason,
        processed_by=current_user.id,
        refund_amount=refund_amount,
        refund_method=body.refund_method,
        status=ReturnStatus.completed,
        notes=body.notes,
        completed_at=now,
    )
    db.add(ret)
    await db.flush()

    return_items_out = []
    for item_id in body.item_ids:
        si = sale_items_map[item_id]
        ri = ReturnItem(
            return_id=ret.id,
            item_id=item_id,
            original_price=si.price,
            refund_price=si.price,  # full refund by default
        )
        db.add(ri)
        return_items_out.append(ri)

        # Update item status
        item = items[item_id]
        # Guard: don't blindly flip archived items to in_stock
        if body.resellable and item.status != ItemStatus.archived:
            item.status = ItemStatus.in_stock
            item.sold_at = None
        elif not body.resellable:
            item.status = ItemStatus.archived

    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="One or more items have already been returned",
        )

    await write_audit_log(
        db,
        table_name="returns",
        record_id=ret.id,
        action="INSERT",
        user_id=current_user.id,
        new_values={
            "return_ref": return_ref,
            "sale_ref": body.sale_ref,
            "item_count": len(body.item_ids),
            "refund_amount": str(refund_amount),
        },
        ip_address=request.client.host if request.client else None,
    )

    await db.commit()
    await db.refresh(ret)

    return ReturnResponse(
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
        items=[
            ReturnItemResponse(
                id=ri.id,
                item_id=ri.item_id,
                original_price=ri.original_price,
                refund_price=ri.refund_price,
            )
            for ri in return_items_out
        ],
    )


@router.get("/{return_ref}", response_model=ReturnResponse)
async def get_return(
    return_ref: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Return).where(Return.return_ref == return_ref))
    ret = result.scalar_one_or_none()
    if ret is None:
        raise HTTPException(status_code=404, detail="Return not found")

    items_result = await db.execute(select(ReturnItem).where(ReturnItem.return_id == ret.id))
    return_items = items_result.scalars().all()

    return ReturnResponse(
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
        items=[
            ReturnItemResponse(
                id=ri.id,
                item_id=ri.item_id,
                original_price=ri.original_price,
                refund_price=ri.refund_price,
            )
            for ri in return_items
        ],
    )
