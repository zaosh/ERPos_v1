from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import require_admin
from models.user import User
from schemas.analytics import (
    AnalyticsPeriod,
    CVPerformanceResponse,
    DeadStockItem,
    SummaryResponse,
    TrendsResponse,
    VelocityRow,
)
from services import analytics_service
from services.image_service import get_image_url

router = APIRouter()


@router.get("/summary", response_model=SummaryResponse)
async def summary(
    period: AnalyticsPeriod = "30d",
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    data = await analytics_service.get_summary(db, period)
    return SummaryResponse(**data)


@router.get("/trends", response_model=TrendsResponse)
async def trends(
    group_by: str = Query("category", pattern="^(label|color|category)$"),
    period: AnalyticsPeriod = "30d",
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    data = await analytics_service.get_trends(db, group_by, period)
    return TrendsResponse(**data)


@router.get("/dead_stock", response_model=list[DeadStockItem])
async def dead_stock(
    days: int = Query(21, ge=1, le=365),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = await analytics_service.get_dead_stock(db, days)
    return [
        DeadStockItem(
            id=r["id"],
            barcode=r["barcode"],
            category=str(r["category"]),
            color=r.get("color"),
            label=r.get("label"),
            size=r.get("size"),
            condition=str(r["condition"]),
            price=r["price"],
            days_in_stock=r["days_in_stock"],
            image_thumb_url=get_image_url(r.get("image_thumb_path")),
        )
        for r in rows
    ]


@router.get("/velocity", response_model=list[VelocityRow])
async def velocity(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = await analytics_service.get_velocity(db)
    return [VelocityRow(**r) for r in rows]


@router.get("/cv-performance", response_model=CVPerformanceResponse)
async def cv_performance(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    data = await analytics_service.get_cv_performance(db)
    return CVPerformanceResponse(**data)
