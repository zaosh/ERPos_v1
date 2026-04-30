import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from schemas.analytics import AnalyticsPeriod

logger = logging.getLogger(__name__)

_PERIOD_DAYS = {"7d": 7, "30d": 30, "90d": 90}


def _period_start(period: str) -> datetime:
    days = _PERIOD_DAYS.get(period, 30)
    return datetime.now(timezone.utc) - timedelta(days=days)


async def get_summary(db: AsyncSession, period: AnalyticsPeriod) -> dict[str, Any]:
    since = _period_start(period)

    result = await db.execute(
        text("""
            SELECT
                COUNT(*) FILTER (WHERE deleted_at IS NULL) AS total_items,
                COUNT(*) FILTER (WHERE status = 'sold' AND sold_at >= :since AND deleted_at IS NULL) AS sold,
                COUNT(*) FILTER (WHERE status = 'in_stock' AND deleted_at IS NULL) AS in_stock,
                COALESCE(SUM(price) FILTER (WHERE status = 'sold' AND sold_at >= :since AND deleted_at IS NULL), 0) AS revenue,
                COALESCE(AVG(price) FILTER (WHERE status = 'sold' AND sold_at >= :since AND deleted_at IS NULL), 0) AS avg_price
            FROM items
        """),
        {"since": since},
    )
    row = result.mappings().one()

    labels_result = await db.execute(
        text("""
            SELECT
                COALESCE(label, 'unlabeled') AS label,
                COUNT(*) FILTER (WHERE status = 'sold') AS sold_count,
                COUNT(*) AS total,
                ROUND(
                    COUNT(*) FILTER (WHERE status = 'sold') * 100.0 / NULLIF(COUNT(*), 0),
                    1
                ) AS sell_through_pct
            FROM items
            WHERE deleted_at IS NULL AND created_at >= :since
            GROUP BY label
            ORDER BY sold_count DESC
            LIMIT 10
        """),
        {"since": since},
    )
    top_labels = [
        {"label": r["label"], "count": r["total"], "sell_through_pct": float(r["sell_through_pct"] or 0)}
        for r in labels_result.mappings()
    ]

    return {
        "total_items": row["total_items"],
        "sold": row["sold"],
        "in_stock": row["in_stock"],
        "revenue": Decimal(str(row["revenue"])),
        "avg_price": Decimal(str(row["avg_price"])),
        "top_labels": top_labels,
    }


async def get_trends(db: AsyncSession, group_by: str, period: AnalyticsPeriod) -> dict[str, Any]:
    if group_by not in ("label", "color", "category"):
        group_by = "category"

    since = _period_start(period)

    result = await db.execute(
        text(f"""
            SELECT
                COALESCE({group_by}::text, 'unknown') AS group_key,
                DATE_TRUNC('day', sold_at AT TIME ZONE 'UTC')::date AS day,
                COUNT(*) AS count,
                COALESCE(SUM(price), 0) AS revenue
            FROM items
            WHERE status = 'sold'
              AND sold_at >= :since
              AND deleted_at IS NULL
            GROUP BY group_key, day
            ORDER BY group_key, day
        """),
        {"since": since},
    )

    groups: dict[str, list] = {}
    for row in result.mappings():
        gk = row["group_key"]
        if gk not in groups:
            groups[gk] = []
        groups[gk].append({
            "date": row["day"],
            "count": row["count"],
            "revenue": Decimal(str(row["revenue"])),
        })

    return {
        "group_by": group_by,
        "period": period,
        "data": [{"group_key": k, "points": v} for k, v in groups.items()],
    }


async def get_dead_stock(db: AsyncSession, days: int) -> list[dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    result = await db.execute(
        text("""
            SELECT
                id, barcode, category, color, label, size, condition, price,
                image_thumb_path,
                EXTRACT(DAY FROM NOW() - created_at)::int AS days_in_stock
            FROM items
            WHERE status = 'in_stock'
              AND created_at < :cutoff
              AND deleted_at IS NULL
            ORDER BY created_at ASC
        """),
        {"cutoff": cutoff},
    )

    return [dict(r) for r in result.mappings()]


async def get_velocity(db: AsyncSession) -> list[dict[str, Any]]:
    result = await db.execute(
        text("""
            SELECT
                category::text,
                condition::text,
                ROUND(AVG(EXTRACT(EPOCH FROM (sold_at - created_at)) / 86400.0)::numeric, 1) AS avg_days_to_sell,
                COUNT(*) AS sample_size
            FROM items
            WHERE status = 'sold'
              AND sold_at IS NOT NULL
              AND deleted_at IS NULL
            GROUP BY category, condition
            HAVING COUNT(*) >= 2
            ORDER BY avg_days_to_sell ASC
        """),
    )

    return [
        {
            "category": r["category"],
            "condition": r["condition"],
            "avg_days_to_sell": float(r["avg_days_to_sell"]),
            "sample_size": r["sample_size"],
        }
        for r in result.mappings()
    ]
