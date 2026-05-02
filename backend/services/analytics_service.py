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
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    result = await db.execute(
        text("""
            SELECT
                COUNT(*) FILTER (WHERE deleted_at IS NULL) AS total_items,
                COUNT(*) FILTER (WHERE status = 'sold' AND sold_at >= :since AND deleted_at IS NULL) AS sold,
                COUNT(*) FILTER (WHERE status = 'in_stock' AND deleted_at IS NULL) AS in_stock,
                COALESCE(SUM(price) FILTER (WHERE status = 'sold' AND sold_at >= :since AND deleted_at IS NULL), 0) AS revenue,
                COALESCE(AVG(price) FILTER (WHERE status = 'sold' AND sold_at >= :since AND deleted_at IS NULL), 0) AS avg_price,
                COUNT(*) FILTER (WHERE status = 'sold' AND sold_at >= :today AND deleted_at IS NULL) AS today_items,
                COALESCE(SUM(price) FILTER (WHERE status = 'sold' AND sold_at >= :today AND deleted_at IS NULL), 0) AS today_revenue
            FROM items
        """),
        {"since": since, "today": today_start},
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
        "today_items": row["today_items"],
        "today_revenue": Decimal(str(row["today_revenue"])),
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


async def get_cv_performance(db: AsyncSession) -> dict[str, Any]:
    result = await db.execute(
        text("""
            SELECT
                COUNT(*) FILTER (WHERE cv_color_correct IS NOT NULL) AS color_total,
                COUNT(*) FILTER (WHERE cv_color_correct = true) AS color_correct,
                COUNT(*) FILTER (WHERE cv_type_correct IS NOT NULL) AS type_total,
                COUNT(*) FILTER (WHERE cv_type_correct = true) AS type_correct,
                COUNT(*) FILTER (WHERE cv_raw_output IS NOT NULL) AS total_analyzed,
                COUNT(*) FILTER (WHERE cv_confidence IS NOT NULL AND cv_confidence < 0.4) AS needs_review_count,
                COUNT(*) AS total_items,
                COUNT(*) FILTER (
                    WHERE label IS NOT NULL AND label != '' AND label != 'unknown'
                    AND cv_raw_output IS NOT NULL
                ) AS label_identified
            FROM items
            WHERE deleted_at IS NULL
        """),
    )
    row = result.mappings().one()

    total_analyzed = row["total_analyzed"] or 0
    color_total = row["color_total"] or 0
    type_total = row["type_total"] or 0
    color_accuracy = float(row["color_correct"]) / color_total if color_total > 0 else 0.0
    type_accuracy = float(row["type_correct"]) / type_total if type_total > 0 else 0.0
    label_accuracy = float(row["label_identified"]) / total_analyzed if total_analyzed > 0 else 0.0
    overall_accuracy = (color_accuracy + type_accuracy + label_accuracy) / 3

    needs_review_pct = (
        float(row["needs_review_count"]) / total_analyzed * 100
        if total_analyzed > 0 else 0.0
    )

    # Confidence calibration buckets
    cal_result = await db.execute(
        text("""
            SELECT
                CASE
                    WHEN cv_confidence < 0.4 THEN 'low'
                    WHEN cv_confidence < 0.65 THEN 'medium'
                    ELSE 'high'
                END AS bucket,
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE cv_color_correct = true OR cv_type_correct = true) AS correct
            FROM items
            WHERE cv_confidence IS NOT NULL AND deleted_at IS NULL
            GROUP BY bucket
        """),
    )
    bucket_map = {r["bucket"]: r for r in cal_result.mappings()}
    calibration = []
    for label, range_str, key in [
        ("Low confidence", "0.0–0.4", "low"),
        ("Medium confidence", "0.4–0.65", "medium"),
        ("High confidence", "0.65–1.0", "high"),
    ]:
        b = bucket_map.get(key)
        total = int(b["total"]) if b else 0
        correct = int(b["correct"]) if b else 0
        calibration.append({
            "label": label,
            "range": range_str,
            "total": total,
            "correct": correct,
            "accuracy": float(correct) / total if total > 0 else 0.0,
        })

    # Top mistakes
    mistakes_result = await db.execute(
        text("""
            (
                SELECT
                    'color' AS field,
                    cv_raw_output->>'color' AS cv_suggested,
                    color AS human_confirmed,
                    COUNT(*) AS cnt
                FROM items
                WHERE cv_color_correct = false
                  AND cv_raw_output->>'color' IS NOT NULL
                  AND color IS NOT NULL
                  AND deleted_at IS NULL
                GROUP BY cv_suggested, human_confirmed
            )
            UNION ALL
            (
                SELECT
                    'type' AS field,
                    cv_raw_output->>'type' AS cv_suggested,
                    type::text AS human_confirmed,
                    COUNT(*) AS cnt
                FROM items
                WHERE cv_type_correct = false
                  AND cv_raw_output->>'type' IS NOT NULL
                  AND deleted_at IS NULL
                GROUP BY cv_suggested, human_confirmed
            )
            ORDER BY cnt DESC
            LIMIT 10
        """),
    )
    top_mistakes = [
        {
            "field": r["field"],
            "cv_suggested": r["cv_suggested"],
            "human_confirmed": r["human_confirmed"],
            "count": r["cnt"],
        }
        for r in mistakes_result.mappings()
    ]

    return {
        "color_accuracy": color_accuracy,
        "type_accuracy": type_accuracy,
        "label_accuracy": label_accuracy,
        "overall_accuracy": overall_accuracy,
        "confidence_calibration": calibration,
        "top_mistakes": top_mistakes,
        "total_items_analyzed": total_analyzed,
        "items_needing_review_pct": needs_review_pct,
    }


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
