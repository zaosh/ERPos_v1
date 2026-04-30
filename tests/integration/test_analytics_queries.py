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
