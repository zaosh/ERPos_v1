"""
Exchange service — core logic for the exchange flow.

Key invariants:
- exchange_eligible is set once at purchase time; never changed after.
- An item can only be exchanged once (UNIQUE constraint on exchanges.original_item_id).
- exchange always requires a known customer.
- image_confirmed must be True before any exchange row is created.
- is_exchange_item = True is one-way; never cleared.
"""
import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.customer import Customer
from models.exchange import BillEventType, BillHistory, Exchange, ExchangeStatus, ReturnedItemCondition
from models.item import Item, ItemStatus
from models.sale import Sale, SaleItem
from services import settings_service


class ExchangeNotEligibleError(Exception):
    """Raised when an item cannot be exchanged. Route layer maps to HTTP 422."""

    def __init__(self, code: str, detail: str):
        self.code = code  # NOT_ON_SALE | NOT_ELIGIBLE | WINDOW_EXPIRED | ALREADY_EXCHANGED | NOT_SOLD
        self.detail = detail
        super().__init__(detail)


def _advisory_key(prefix: str) -> int:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    raw = hashlib.blake2b(f"{prefix}:{today}".encode(), digest_size=8).digest()
    val = int.from_bytes(raw, "big")
    if val >= 2**63:
        val -= 2**64
    return val


async def generate_exchange_ref(db: AsyncSession) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    key = _advisory_key("exc")
    await db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": key})
    n = await db.scalar(
        text("SELECT COUNT(*) FROM exchanges WHERE exchange_ref LIKE :p"),
        {"p": f"EXC-{today}-%"},
    )
    seq = (n or 0) + 1
    if seq > 9999:
        raise HTTPException(status_code=409, detail="Exchange ref sequence exhausted for today")
    return f"EXC-{today}-{seq:04d}"


async def validate_exchange_eligibility(
    item_id: int, sale_id: int, customer_id: int, db: AsyncSession
) -> None:
    """Validate that an item can be exchanged. Raises ExchangeNotEligibleError on failure."""

    # 1. Check sale belongs to the customer (or was linked via link-customer)
    sale = await db.scalar(select(Sale).where(Sale.id == sale_id))
    if sale is None:
        raise ExchangeNotEligibleError("NOT_ON_SALE", "Sale not found")
    if sale.voided_at is not None:
        raise ExchangeNotEligibleError("NOT_ON_SALE", "Sale is voided — exchange not allowed")
    if sale.customer_id != customer_id:
        raise ExchangeNotEligibleError(
            "NOT_ON_SALE",
            "This sale is not linked to the specified customer — use POST /sales/{ref}/link-customer first",
        )

    # 2. Item must be on this sale
    sale_item = await db.scalar(
        select(SaleItem).where(
            SaleItem.sale_id == sale_id,
            SaleItem.item_id == item_id,
        )
    )
    if sale_item is None:
        raise ExchangeNotEligibleError(
            "NOT_ON_SALE", f"Item {item_id} was not part of sale {sale_id}"
        )

    # 3. Item must have exchange_eligible = True
    item = await db.scalar(select(Item).where(Item.id == item_id))
    if item is None:
        raise ExchangeNotEligibleError("NOT_ELIGIBLE", f"Item {item_id} not found")
    if not item.exchange_eligible:
        raise ExchangeNotEligibleError(
            "NOT_ELIGIBLE",
            "This item was not opted in for exchange at the time of purchase",
        )

    # 4. Item must be in sold status
    if item.status != ItemStatus.sold:
        if item.status == ItemStatus.exchanged:
            raise ExchangeNotEligibleError(
                "ALREADY_EXCHANGED", "This item has already been exchanged"
            )
        raise ExchangeNotEligibleError(
            "NOT_SOLD", f"Item status is {item.status.value} — must be 'sold' to exchange"
        )

    # 5. No existing pending/completed exchange for this item
    existing = await db.scalar(
        select(Exchange).where(
            Exchange.original_item_id == item_id,
            Exchange.status.in_([ExchangeStatus.pending, ExchangeStatus.completed]),
        )
    )
    if existing is not None:
        raise ExchangeNotEligibleError(
            "ALREADY_EXCHANGED",
            f"An exchange already exists for this item (ref: {existing.exchange_ref})",
        )

    # 6. Check exchange window
    exchange_window_days = await settings_service.get_int(db, "exchange_window_days", default=30)
    now = datetime.now(timezone.utc)
    days_since_sale = (now - sale.created_at).days
    if days_since_sale > exchange_window_days:
        raise ExchangeNotEligibleError(
            "WINDOW_EXPIRED",
            f"Exchange window of {exchange_window_days} days has expired ({days_since_sale} days since purchase)",
        )


async def append_bill_history(
    db: AsyncSession,
    *,
    sale_id: int,
    event_type: BillEventType,
    description: str,
    created_by: int,
    item_id: Optional[int] = None,
    exchange_id: Optional[int] = None,
    return_id: Optional[int] = None,
) -> BillHistory:
    """Append an event to the bill history timeline for a sale."""
    event = BillHistory(
        sale_id=sale_id,
        event_type=event_type,
        item_id=item_id,
        exchange_id=exchange_id,
        return_id=return_id,
        description=description,
        created_by=created_by,
    )
    db.add(event)
    await db.flush()
    return event


async def initiate_exchange(
    *,
    sale_ref: str,
    item_id: int,
    customer_uid: str,
    reason: str,
    condition: ReturnedItemCondition,
    image_confirmed: bool,
    processed_by: int,
    db: AsyncSession,
) -> Exchange:
    """
    Initiate an exchange. Validates eligibility, creates exchange row with status=pending.
    Does NOT change item status yet — that happens at complete_exchange.
    """
    if not image_confirmed:
        raise HTTPException(
            status_code=422,
            detail="image_confirmed must be true — staff must verify the physical item against the stored photo",
        )

    # Resolve sale
    sale = await db.scalar(select(Sale).where(Sale.sale_ref == sale_ref))
    if sale is None:
        raise HTTPException(status_code=404, detail="Sale not found")

    # Resolve customer
    customer = await db.scalar(
        select(Customer).where(
            Customer.customer_uid == customer_uid,
            Customer.gdpr_erased_at.is_(None),
            Customer.is_active.is_(True),
        )
    )
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Validate eligibility (raises ExchangeNotEligibleError → caller maps to 422)
    await validate_exchange_eligibility(item_id, sale.id, customer.id, db)

    # Fetch item for fee amount
    item = await db.scalar(select(Item).where(Item.id == item_id))
    fee = item.exchange_fee_paid or Decimal("0")

    exchange_ref = await generate_exchange_ref(db)

    ex = Exchange(
        exchange_ref=exchange_ref,
        original_sale_id=sale.id,
        original_item_id=item_id,
        customer_id=customer.id,
        exchange_reason=reason,
        returned_item_condition=condition,
        returned_item_image_confirmed=True,
        exchange_fee=fee,
        status=ExchangeStatus.pending,
        processed_by=processed_by,
    )
    db.add(ex)
    await db.flush()

    await append_bill_history(
        db,
        sale_id=sale.id,
        event_type=BillEventType.exchange_initiated,
        item_id=item_id,
        exchange_id=ex.id,
        description=(
            f"Exchange initiated for item {item.barcode} "
            f"(condition: {condition.value}, reason: {reason[:80]})"
        ),
        created_by=processed_by,
    )

    await db.commit()
    await db.refresh(ex)
    return ex


async def complete_exchange(
    *,
    exchange_ref: str,
    new_item_barcode: str,
    processed_by: int,
    db: AsyncSession,
) -> Exchange:
    """
    Complete an exchange by selecting the replacement item.
    Within a single transaction:
    - Sets exchange status = completed
    - Sets original item status = exchanged
    - Sets new item status = sold, is_exchange_item = True, original_item_id = original
    - Appends bill_history event
    """
    ex = await db.scalar(
        select(Exchange).where(Exchange.exchange_ref == exchange_ref).with_for_update()
    )
    if ex is None:
        raise HTTPException(status_code=404, detail="Exchange not found")
    if ex.status != ExchangeStatus.pending:
        raise HTTPException(
            status_code=409,
            detail=f"Exchange is already {ex.status.value} — cannot complete",
        )

    # Validate new item
    new_item = await db.scalar(
        select(Item).where(
            Item.barcode == new_item_barcode,
            Item.deleted_at.is_(None),
        ).with_for_update()
    )
    if new_item is None:
        raise HTTPException(status_code=404, detail=f"Item with barcode {new_item_barcode} not found")
    if new_item.status != ItemStatus.in_stock:
        raise HTTPException(
            status_code=422,
            detail=f"Item {new_item_barcode} is not in stock (status: {new_item.status.value})",
        )

    # Get original item
    original_item = await db.scalar(
        select(Item).where(Item.id == ex.original_item_id).with_for_update()
    )
    if original_item is None:
        raise HTTPException(status_code=500, detail="Original item not found — data integrity error")

    now = datetime.now(timezone.utc)

    # Update exchange record
    ex.status = ExchangeStatus.completed
    ex.new_item_id = new_item.id
    ex.completed_at = now

    # Update original item: mark as exchanged (terminal)
    original_item.status = ItemStatus.exchanged
    original_item.exchanged_at = now

    # Update new item: sold, tagged as exchange item
    new_item.status = ItemStatus.sold
    new_item.sold_at = now
    new_item.is_exchange_item = True
    new_item.original_item_id = original_item.id

    await db.flush()

    await append_bill_history(
        db,
        sale_id=ex.original_sale_id,
        event_type=BillEventType.exchange_completed,
        item_id=new_item.id,
        exchange_id=ex.id,
        description=(
            f"Exchange completed on {now.strftime('%d/%m/%Y')}. "
            f"Original item {original_item.barcode} returned. "
            f"New item {new_item.barcode} taken."
        ),
        created_by=processed_by,
    )

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Exchange could not be completed — item may have already been used in another exchange",
        )

    await db.refresh(ex)
    return ex


async def get_bill_history(sale_id: int, db: AsyncSession) -> list[BillHistory]:
    """Return all history events for a sale in chronological order."""
    result = await db.execute(
        select(BillHistory)
        .where(BillHistory.sale_id == sale_id)
        .order_by(BillHistory.created_at.asc(), BillHistory.id.asc())
    )
    return list(result.scalars().all())
