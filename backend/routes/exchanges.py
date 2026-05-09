import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import require_admin, require_staff
from models.customer import Customer
from models.exchange import Exchange
from models.user import User
from schemas.exchange import (
    BillHistoryEvent,
    ExchangeComplete,
    ExchangeInitiate,
    ExchangeResponse,
)
from services.exchange_service import (
    ExchangeNotEligibleError,
    complete_exchange,
    get_bill_history,
    initiate_exchange,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/initiate", response_model=ExchangeResponse, status_code=201)
async def initiate_exchange_route(
    body: ExchangeInitiate,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """
    Initiate an exchange.
    Requires: sale_ref + item_id on that sale + customer_uid matching the sale,
    staff confirmation that physical item matches stored photo.
    """
    try:
        ex = await initiate_exchange(
            sale_ref=body.sale_ref,
            item_id=body.item_id,
            customer_uid=body.customer_uid,
            reason=body.exchange_reason,
            condition=body.returned_condition,
            image_confirmed=body.image_confirmed,
            processed_by=current_user.id,
            db=db,
        )
    except ExchangeNotEligibleError as e:
        raise HTTPException(status_code=422, detail={"code": e.code, "message": e.detail})
    return ex


@router.post("/{exchange_ref}/complete", response_model=ExchangeResponse)
async def complete_exchange_route(
    exchange_ref: str,
    body: ExchangeComplete,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """
    Complete an exchange by providing the barcode of the replacement item.
    The replacement item must be in_stock.
    """
    try:
        ex = await complete_exchange(
            exchange_ref=exchange_ref,
            new_item_barcode=body.new_item_barcode,
            processed_by=current_user.id,
            db=db,
        )
    except ExchangeNotEligibleError as e:
        raise HTTPException(status_code=422, detail={"code": e.code, "message": e.detail})
    return ex


@router.get("/{exchange_ref}", response_model=ExchangeResponse)
async def get_exchange(
    exchange_ref: str,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    ex = await db.scalar(select(Exchange).where(Exchange.exchange_ref == exchange_ref))
    if ex is None:
        raise HTTPException(status_code=404, detail="Exchange not found")
    return ex


@router.get("/{exchange_ref}/history", response_model=list[BillHistoryEvent])
async def get_exchange_history(
    exchange_ref: str,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    ex = await db.scalar(select(Exchange).where(Exchange.exchange_ref == exchange_ref))
    if ex is None:
        raise HTTPException(status_code=404, detail="Exchange not found")
    events = await get_bill_history(ex.original_sale_id, db)
    return events
