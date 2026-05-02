import logging
import tempfile
import os
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from config import settings
from database import get_db
from dependencies import get_redis, require_admin, require_staff
from middleware.audit import write_audit_log
from models.item import Item, ItemStatus, ItemType
from models.job_queue import JobType
from models.user import User
from schemas.item import (
    CaptureResponse,
    ItemCreate,
    ItemCreateResponse,
    ItemListResponse,
    ItemResponse,
    ItemUpdate,
)
from services.barcode_service import generate_barcode
from services.cv_service import detect_color
from services.image_service import (
    claim_temp_image as _claim_temp_image,
    get_image_url,
    save_temp_image,
    validate_image,
)
from services.printer_service import generate_zpl
from services.queue_service import enqueue

logger = logging.getLogger(__name__)
router = APIRouter()


def _item_to_response(item: Item) -> dict:
    return {
        "id": item.id,
        "barcode": item.barcode,
        "category": item.category,
        "color": item.color,
        "secondary_color": item.secondary_color,
        "type": item.type,
        "label": item.label,
        "size": item.size,
        "condition": item.condition,
        "price": item.price,
        "cv_confidence": item.cv_confidence,
        "cv_raw_output": item.cv_raw_output,
        "image_path": item.image_path,
        "image_thumb_path": item.image_thumb_path,
        "image_url": get_image_url(item.image_path),
        "image_thumb_url": get_image_url(item.image_thumb_path),
        "status": item.status,
        "notes": item.notes,
        "created_by": item.created_by,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "sold_at": item.sold_at,
    }


@router.post("/capture", response_model=CaptureResponse)
async def capture_image(
    image: UploadFile = File(...),
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    redis_client: aioredis.Redis = Depends(get_redis),
):
    """
    Save uploaded image as temp, run K-means color detection (~50ms).
    Type analysis happens after item creation via cv_phase_a job.
    """
    image_bytes = await validate_image(image)
    temp_id = await save_temp_image(image_bytes, current_user.id, redis_client)

    # Detect color locally — fast, no API cost
    color = None
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    try:
        tmp.write(image_bytes)
        tmp.flush()
        tmp.close()
        color = await detect_color(tmp.name)
    except Exception as e:
        logger.warning(f"Color detection failed at capture: {e}")
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

    return CaptureResponse(temp_image_id=temp_id, color=color)


@router.post("/", response_model=ItemCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_item(
    body: ItemCreate,
    request: Request,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    redis_client: aioredis.Redis = Depends(get_redis),
):
    """
    Create item, then enqueue cv_phase_a and print_label jobs.
    Returns immediately with job_ids for frontend polling.
    """
    barcode = await generate_barcode(redis_client)

    item = Item(
        barcode=barcode,
        category=body.category,
        color=body.color,
        secondary_color=body.secondary_color,
        type=body.type,  # defaults to 'unknown'; worker fills it via cv_phase_a
        label=body.label,
        size=body.size,
        condition=body.condition,
        price=body.price,
        notes=body.notes,
        status=ItemStatus.in_stock,
        created_by=current_user.id,
    )
    db.add(item)

    try:
        await db.flush()
    except Exception:
        await db.rollback()
        barcode = await generate_barcode(redis_client)
        item.barcode = barcode
        db.add(item)
        await db.flush()

    # Claim temp image → permanent path
    try:
        image_path, thumb_path = await _claim_temp_image(
            body.temp_image_id, current_user.id, item.id, redis_client
        )
        item.image_path = image_path
        item.image_thumb_path = thumb_path
    except HTTPException as e:
        if e.status_code == 410:
            logger.warning(f"Temp image {body.temp_image_id} expired — item saved without image")
            image_path = None
        else:
            await db.rollback()
            raise

    await write_audit_log(
        db,
        table_name="items",
        record_id=item.id,
        action="INSERT",
        user_id=current_user.id,
        new_values={
            "barcode": item.barcode,
            "category": item.category.value,
            "price": str(item.price),
            "status": item.status.value,
        },
        ip_address=request.client.host if request.client else None,
    )

    await db.commit()
    await db.refresh(item)

    # Enqueue CV phase A (priority 1 — worker picks this up ASAP)
    cv_job_id = None
    if item.image_path:
        cv_job_id = await enqueue(
            db,
            job_type=JobType.cv_phase_a,
            payload={"image_path": item.image_path},
            item_id=item.id,
            priority=1,
            max_attempts=3,
            created_by=current_user.id,
        )

    # Generate ZPL at enqueue time — stored in payload so printer retry doesn't regenerate
    zpl = generate_zpl(item)
    print_job_id = await enqueue(
        db,
        job_type=JobType.print_label,
        payload={"item_id": item.id, "barcode": item.barcode, "zpl": zpl},
        item_id=item.id,
        priority=1,
        max_attempts=settings.PRINT_QUEUE_MAX_ATTEMPTS,
        created_by=current_user.id,
    )

    await db.commit()

    response_data = _item_to_response(item)
    response_data["cv_job_id"] = cv_job_id
    response_data["print_job_id"] = print_job_id
    return response_data


@router.get("/{item_id}", response_model=ItemResponse)
async def get_item(
    item_id: int,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Item).where(Item.id == item_id, Item.deleted_at.is_(None))
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return _item_to_response(item)


@router.get("/", response_model=ItemListResponse)
async def list_items(
    status: Optional[ItemStatus] = None,
    category: Optional[str] = None,
    color: Optional[str] = None,
    label: Optional[str] = None,
    barcode: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    query = select(Item).where(Item.deleted_at.is_(None))

    if status:
        query = query.where(Item.status == status)
    if category:
        query = query.where(Item.category == category)
    if color:
        query = query.where(Item.color == color)
    if label:
        query = query.where(Item.label.ilike(f"%{label}%"))
    if barcode:
        query = query.where(Item.barcode == barcode)

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar_one()

    result = await db.execute(query.offset(offset).limit(limit).order_by(Item.created_at.desc()))
    items = result.scalars().all()

    return ItemListResponse(
        items=[_item_to_response(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch("/{barcode}", response_model=ItemResponse)
async def update_item(
    barcode: str,
    body: ItemUpdate,
    request: Request,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Item).where(Item.barcode == barcode, Item.deleted_at.is_(None))
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")

    old_values = {
        "price": str(item.price),
        "condition": item.condition.value,
        "status": item.status.value,
    }
    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(item, field, value)

    await write_audit_log(
        db,
        table_name="items",
        record_id=item.id,
        action="UPDATE",
        user_id=current_user.id,
        old_values=old_values,
        new_values=update_data,
        ip_address=request.client.host if request.client else None,
    )

    await db.commit()
    await db.refresh(item)
    return _item_to_response(item)


@router.post("/{item_id}/reprint")
async def reprint_label(
    item_id: int,
    request: Request,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """Enqueue a print_retry job for an item."""
    result = await db.execute(
        select(Item).where(Item.id == item_id, Item.deleted_at.is_(None))
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")

    zpl = generate_zpl(item)
    job_id = await enqueue(
        db,
        job_type=JobType.print_retry,
        payload={"item_id": item.id, "barcode": item.barcode, "zpl": zpl},
        item_id=item.id,
        priority=2,
        max_attempts=settings.PRINT_QUEUE_MAX_ATTEMPTS,
        created_by=current_user.id,
    )
    await db.commit()
    return {"queued": True, "print_job_id": job_id, "barcode": item.barcode}
