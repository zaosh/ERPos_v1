from datetime import date
from decimal import Decimal
from typing import Literal, Optional
from pydantic import BaseModel

AnalyticsPeriod = Literal["7d", "30d", "90d"]


class TopLabel(BaseModel):
    label: str
    count: int
    sell_through_pct: float


class SummaryResponse(BaseModel):
    total_items: int
    sold: int
    in_stock: int
    revenue: Decimal
    avg_price: Decimal
    top_labels: list[TopLabel]


class TrendPoint(BaseModel):
    date: date
    count: int
    revenue: Decimal


class TrendGroup(BaseModel):
    group_key: str
    points: list[TrendPoint]


class TrendsResponse(BaseModel):
    group_by: str
    period: str
    data: list[TrendGroup]


class DeadStockItem(BaseModel):
    id: int
    barcode: str
    category: str
    color: Optional[str]
    label: Optional[str]
    size: Optional[str]
    condition: str
    price: Decimal
    days_in_stock: int
    image_thumb_url: Optional[str]


class VelocityRow(BaseModel):
    category: str
    condition: str
    avg_days_to_sell: float
    sample_size: int
