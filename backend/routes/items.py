import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as aioredis

from database import get_db
from dependencies import get_current_user, get_redis, require_admin, require_staff
from middleware.audit import write_audit_log
from models.item import Item, ItemStatus
from models.user import User
from schemas.item import (
    CaptureResponse,
    CVResult,
    ItemCreate,
    ItemCreateResponse,
    ItemListResponse,
    ItemResponse,
    ItemUpdate,
)
from services.barcode_service import generate_barcode
from services.cv_service import analyze_image
from services.image_service import (
    claim_temp_image as _claim_temp_image,
    get_image_url,
    save_temp_image,
    validate_image,
)
from services.printer_service import build_zpl_label, print_label

logger = logging.getLogger(__name__)
router = APIRouter()


async def finalize_image(
    temp_image_id: str, user_id: int, item_id: int, redis_client: aioredis.Redis
) -> tuple[str, str]:
    return await _claim_temp_image(temp_image_id, user_id, item_id, redis_client)


def _item_to_response(item: Item) -> dict:
    d = {
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
    return d


@router.post("/capture", response_model=CaptureResponse)
async def capture_image(
    image: UploadFile = File(...),
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    redis_client: aioredis.Redis = Depends(get_redis),
):
    image_bytes = await validate_image(image)

    temp_id = await save_temp_image(image_bytes, current_user.id, redis_client)

    import tempfile, os
    from pathlib import Path
    temp_path = str(Path(image.filename or "temp.jpg"))

    import io
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    tmp.write(image_bytes)
    tmp.flush()
    tmp_path = tmp.name
    tmp.close()

    try:
        cv_result = await analyze_image(tmp_path)
    finally:
        os.unlink(tmp_path)

    return CaptureResponse(
        cv_result=CVResult(
            color=cv_result.get("color"),
            type=cv_result.get("type"),
            confidence=cv_result.get("confidence", 0.0),
            needs_review=cv_result.get("needs_review", True),
        ),
        temp_image_id=temp_id,
    )


@router.post("/", response_model=ItemCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_item(
    body: ItemCreate,
    request: Request,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    redis_client: aioredis.Redis = Depends(get_redis),
):
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

    try:
        image_path, thumb_path = await finalize_image(
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

    zpl = build_zpl_label(
        barcode=item.barcode,
        price=item.price,
        category=item.category.value,
        color=item.color,
        size=item.size,
    )
    label_printed = await print_label(zpl, item.id, item.barcode, redis_client)

    response_data = _item_to_response(item)
    response_data["label_printed"] = label_printed
    response_data["item_id"] = item.id
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
    from models.item import ItemCategory
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


@router.patch("/{item_id}", response_model=ItemResponse)
async def update_item(
    item_id: int,
    body: ItemUpdate,
    request: Request,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Item).where(Item.id == item_id, Item.deleted_at.is_(None))
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
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    redis_client: aioredis.Redis = Depends(get_redis),
):
    result = await db.execute(
        select(Item).where(Item.id == item_id, Item.deleted_at.is_(None))
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")

    zpl = build_zpl_label(
        barcode=item.barcode,
        price=item.price,
        category=item.category.value,
        color=item.color,
        size=item.size,
    )
    success = await print_label(zpl, item.id, item.barcode, redis_client)
    return {"printed": success, "barcode": item.barcode}
