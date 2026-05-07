import base64
import logging
import tempfile
import os
import uuid
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
from models.return_ import ReturnItem
from models.job_queue import JobType
from models.user import User
from schemas.item import (
    BulkItemCreateResponse,
    CaptureResponse,
    ItemCreate,
    ItemCreateResponse,
    ItemListResponse,
    ItemResponse,
    ItemUpdate,
)
from services.barcode_service import generate_barcode, generate_barcode_image
from services.cv_service import detect_color
from services.image_service import (
    claim_temp_image as _claim_temp_image,
    get_image_url,
    save_temp_image,
    validate_image,
)
from services.printer_service import generate_zpl
from services.queue_service import enqueue
from services.storage_service import get_storage

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


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_item(
    body: ItemCreate,
    request: Request,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    redis_client: aioredis.Redis = Depends(get_redis),
):
    """
    Create item(s). If quantity > 1, creates N items atomically (all or nothing).
    Returns immediately with job_ids for frontend polling.
    """
    if body.quantity == 1:
        return await _create_single(body, request, current_user, db, redis_client)
    else:
        return await _create_bulk(body, request, current_user, db, redis_client)


async def _create_single(
    body: ItemCreate,
    request: Request,
    current_user,
    db: AsyncSession,
    redis_client: aioredis.Redis,
) -> dict:
    barcode = await generate_barcode(redis_client)

    item = Item(
        barcode=barcode,
        category=body.category,
        color=body.color,
        secondary_color=body.secondary_color,
        type=body.type,
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

    image_path = None
    try:
        image_path, thumb_path = await _claim_temp_image(
            body.temp_image_id, current_user.id, item.id, redis_client
        )
        item.image_path = image_path
        item.image_thumb_path = thumb_path
    except HTTPException as e:
        if e.status_code == 410:
            logger.warning(f"Temp image {body.temp_image_id} expired — item saved without image")
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

    barcode_image_b64: Optional[str] = None
    try:
        img_bytes = generate_barcode_image(item.barcode)
        if img_bytes:
            barcode_image_b64 = base64.b64encode(img_bytes).decode()
    except Exception as e:
        logger.warning(f"Barcode image generation failed for item {item.id}: {e}")

    response_data = _item_to_response(item)
    response_data["cv_job_id"] = cv_job_id
    response_data["print_job_id"] = print_job_id
    response_data["barcode_image"] = barcode_image_b64
    return response_data


async def _create_bulk(
    body: ItemCreate,
    request: Request,
    current_user,
    db: AsyncSession,
    redis_client: aioredis.Redis,
) -> dict:
    """
    Create N items atomically. If any item fails, all are rolled back.
    Enqueues ONE cv_phase_a job shared by the whole batch, N print_label jobs.
    """
    bulk_group_id = uuid.uuid4()
    quantity = body.quantity

    # Claim temp image ONCE for the batch; on rollback we must clean it up
    image_path: Optional[str] = None
    thumb_path: Optional[str] = None

    # We need a first item ID to claim the image. Flush a placeholder, claim, then create the rest.
    # Strategy: create all items first without image, then claim image for item[0] and duplicate.
    items: list[Item] = []
    barcodes: list[str] = []

    try:
        for seq in range(1, quantity + 1):
            barcode = await generate_barcode(redis_client)
            item = Item(
                barcode=barcode,
                category=body.category,
                color=body.color,
                secondary_color=body.secondary_color,
                type=body.type,
                label=body.label,
                size=body.size,
                condition=body.condition,
                price=body.price,
                notes=body.notes,
                status=ItemStatus.in_stock,
                created_by=current_user.id,
                bulk_group_id=bulk_group_id,
                bulk_sequence=seq,
            )
            db.add(item)
            items.append(item)
            barcodes.append(barcode)

        await db.flush()  # Get all IDs

        # Claim temp image for item[0], duplicate for items 1..N-1
        storage = get_storage()
        try:
            image_path, thumb_path = await _claim_temp_image(
                body.temp_image_id, current_user.id, items[0].id, redis_client
            )
            items[0].image_path = image_path
            items[0].image_thumb_path = thumb_path

            for item in items[1:]:
                dup_path, dup_thumb = await storage.duplicate(image_path, item.id)
                item.image_path = dup_path
                item.image_thumb_path = dup_thumb
        except HTTPException as e:
            if e.status_code == 410:
                logger.warning(f"Temp image expired for bulk group {bulk_group_id} — no images")
            else:
                raise

        # Audit log for each item
        for item in items:
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
                    "bulk_group_id": str(bulk_group_id),
                    "bulk_sequence": item.bulk_sequence,
                },
                ip_address=request.client.host if request.client else None,
            )

        await db.commit()
        for item in items:
            await db.refresh(item)

    except Exception:
        await db.rollback()
        # Clean up claimed image if it was moved to permanent storage
        if image_path:
            await get_storage().delete(image_path)
        raise

    item_ids = [item.id for item in items]

    # ONE cv_phase_a job for the whole bulk group
    cv_job_id = None
    if items[0].image_path:
        cv_job_id = await enqueue(
            db,
            job_type=JobType.cv_phase_a,
            payload={
                "image_path": items[0].image_path,
                "bulk_group_id": str(bulk_group_id),
                "item_ids": item_ids,
            },
            item_id=items[0].id,
            priority=1,
            max_attempts=3,
            created_by=current_user.id,
        )

    # N print jobs
    print_job_ids: list[int] = []
    for item in items:
        zpl = generate_zpl(item)
        pjid = await enqueue(
            db,
            job_type=JobType.print_label,
            payload={"item_id": item.id, "barcode": item.barcode, "zpl": zpl},
            item_id=item.id,
            priority=1,
            max_attempts=settings.PRINT_QUEUE_MAX_ATTEMPTS,
            created_by=current_user.id,
        )
        print_job_ids.append(pjid)

    await db.commit()

    # Build response items
    item_responses = []
    for item in items:
        barcode_image_b64: Optional[str] = None
        try:
            img_bytes = generate_barcode_image(item.barcode)
            if img_bytes:
                barcode_image_b64 = base64.b64encode(img_bytes).decode()
        except Exception as e:
            logger.warning(f"Barcode image generation failed for item {item.id}: {e}")

        rd = _item_to_response(item)
        rd["cv_job_id"] = cv_job_id
        rd["print_job_id"] = None  # individual job ids in print_job_ids
        rd["barcode_image"] = barcode_image_b64
        item_responses.append(rd)

    return {
        "bulk_group_id": bulk_group_id,
        "total": quantity,
        "items": item_responses,
        "print_job_ids": print_job_ids,
    }


@router.get("/bulk/{bulk_group_id}", response_model=list[ItemResponse])
async def get_bulk_group(
    bulk_group_id: str,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """Return all items in a bulk group with their current status."""
    try:
        group_uuid = uuid.UUID(bulk_group_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid bulk_group_id format")

    result = await db.execute(
        select(Item)
        .where(Item.bulk_group_id == group_uuid, Item.deleted_at.is_(None))
        .order_by(Item.bulk_sequence)
    )
    items = result.scalars().all()
    if not items:
        raise HTTPException(status_code=404, detail="Bulk group not found")
    return [_item_to_response(i) for i in items]


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
    ri = await db.scalar(select(ReturnItem.item_id).where(ReturnItem.item_id == item.id))
    r = _item_to_response(item)
    r["has_been_returned"] = ri is not None
    return r


@router.get("/", response_model=ItemListResponse)
async def list_items(
    status: Optional[ItemStatus] = None,
    category: Optional[str] = None,
    color: Optional[str] = None,
    label: Optional[str] = None,
    barcode: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import or_
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
    if search:
        query = query.where(
            or_(
                Item.label.ilike(f"%{search}%"),
                Item.barcode.ilike(f"%{search}%"),
            )
        )

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar_one()

    result = await db.execute(query.offset(offset).limit(limit).order_by(Item.created_at.desc()))
    items = result.scalars().all()

    # Bulk-check which items have ever been returned
    item_ids = [i.id for i in items]
    returned_ids: set[int] = set()
    if item_ids:
        ri_result = await db.execute(
            select(ReturnItem.item_id).where(ReturnItem.item_id.in_(item_ids))
        )
        returned_ids = set(ri_result.scalars().all())

    responses = []
    for i in items:
        r = _item_to_response(i)
        r["has_been_returned"] = i.id in returned_ids
        responses.append(r)

    return ItemListResponse(
        items=responses,
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
