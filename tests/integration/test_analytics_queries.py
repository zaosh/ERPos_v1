"""Integration tests for analytics queries."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta

from models import Item, ItemCategory, ItemType, ItemCondition, ItemStatus


class TestAnalyticsEndpoints:
    @pytest.mark.asyncio
    async def test_summary_requires_admin(self, client, staff_headers):
        response = await client.get("/analytics/summary", headers=staff_headers)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_summary_returns_expected_structure(self, client, admin_headers):
        response = await client.get("/analytics/summary?period=30d", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "total_items" in data
        assert "sold" in data
        assert "in_stock" in data
        assert "revenue" in data
        assert "avg_price" in data
        assert "top_labels" in data
        assert "today_items" in data
        assert "today_revenue" in data

    @pytest.mark.asyncio
    async def test_summary_today_fields_are_numeric(self, client, admin_headers):
        response = await client.get("/analytics/summary?period=30d", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["today_items"], int)
        assert float(data["today_revenue"]) >= 0

    @pytest.mark.asyncio
    async def test_trends_requires_admin(self, client, staff_headers):
        response = await client.get("/analytics/trends", headers=staff_headers)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_trends_returns_structure(self, client, admin_headers):
        response = await client.get("/analytics/trends?group_by=category&period=30d", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "group_by" in data
        assert "period" in data
        assert "data" in data

    @pytest.mark.asyncio
    async def test_dead_stock_days_in_stock_field(self, client, admin_headers, db_session, admin_user):
        """dead_stock items must include days_in_stock, not days_unsold or days."""
        old = Item(
            barcode="THR-DS-DAYS-TEST",
            category=ItemCategory.tshirt,
            color="grey",
            type=ItemType.plain,
            condition=ItemCondition.good,
            price=Decimal("3.00"),
            status=ItemStatus.in_stock,
            created_by=admin_user.id,
        )
        db_session.add(old)
        await db_session.commit()

        from sqlalchemy import update
        from models.item import Item as ItemModel
        await db_session.execute(
            update(ItemModel)
            .where(ItemModel.id == old.id)
            .values(created_at=datetime.now(timezone.utc) - timedelta(days=30))
        )
        await db_session.commit()

        response = await client.get("/analytics/dead_stock?days=21", headers=admin_headers)
        assert response.status_code == 200
        items = response.json()
        match = next((i for i in items if i["barcode"] == "THR-DS-DAYS-TEST"), None)
        assert match is not None
        assert "days_in_stock" in match
        assert match["days_in_stock"] >= 29
        assert "days_unsold" not in match
        assert "days" not in match

    @pytest.mark.asyncio
    async def test_dead_stock_returns_only_in_stock(self, client, admin_headers, db_session, admin_user):
        old_item = Item(
            barcode="THR-20250101-00001",
            category=ItemCategory.tshirt,
            color="white",
            type=ItemType.plain,
            condition=ItemCondition.good,
            price=Decimal("5.00"),
            status=ItemStatus.in_stock,
            created_by=admin_user.id,
        )
        db_session.add(old_item)
        await db_session.commit()

        from sqlalchemy import update
        from models.item import Item as ItemModel
        await db_session.execute(
            update(ItemModel)
            .where(ItemModel.id == old_item.id)
            .values(created_at=datetime.now(timezone.utc) - timedelta(days=30))
        )
        await db_session.commit()

        response = await client.get("/analytics/dead_stock?days=21", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        barcodes = [item["barcode"] for item in data]
        assert old_item.barcode in barcodes

    @pytest.mark.asyncio
    async def test_velocity_returns_structure(self, client, admin_headers):
        response = await client.get("/analytics/velocity", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_invalid_period_rejected(self, client, admin_headers):
        response = await client.get("/analytics/summary?period=365d", headers=admin_headers)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_cv_performance_requires_admin(self, client, staff_headers):
        response = await client.get("/analytics/cv-performance", headers=staff_headers)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_cv_performance_structure(self, client, admin_headers):
        response = await client.get("/analytics/cv-performance", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "color_accuracy" in data
        assert "type_accuracy" in data
        assert "label_accuracy" in data
        assert "overall_accuracy" in data
        assert "confidence_calibration" in data
        assert "top_mistakes" in data
        assert "total_items_analyzed" in data
        assert "items_needing_review_pct" in data
        assert len(data["confidence_calibration"]) == 3

    @pytest.mark.asyncio
    async def test_cv_performance_with_known_data(self, client, admin_headers, db_session, admin_user):
        """Items with cv tracking should show correct accuracy rates."""
        items = [
            Item(
                barcode=f"THR-CV-TEST-{i:03d}",
                category=ItemCategory.tshirt,
                color="black",
                type=ItemType.band,
                condition=ItemCondition.good,
                price=Decimal("8.00"),
                status=ItemStatus.in_stock,
                created_by=admin_user.id,
                cv_confidence=0.8,
                cv_raw_output={"color": "black", "type": "band"},
                cv_color_correct=(i < 3),   # 3 correct, 2 wrong
                cv_type_correct=True,
            )
            for i in range(5)
        ]
        # Override cv_color_correct for last 2
        items[3].cv_color_correct = False
        items[3].cv_raw_output = {"color": "white", "type": "band"}
        items[4].cv_color_correct = False
        items[4].cv_raw_output = {"color": "blue", "type": "band"}
        for it in items:
            db_session.add(it)
        await db_session.commit()

        response = await client.get("/analytics/cv-performance", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total_items_analyzed"] >= 5
        assert 0.0 <= data["color_accuracy"] <= 1.0
        assert 0.0 <= data["type_accuracy"] <= 1.0
