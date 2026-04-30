"""Unit tests for analytics_service — uses real test DB with known seed data."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta

from services.analytics_service import get_summary, get_dead_stock, get_velocity


class TestSummary:
    @pytest.mark.asyncio
    async def test_summary_structure(self, db_session):
        result = await get_summary(db_session, "30d")
        assert "total_items" in result
        assert "sold" in result
        assert "in_stock" in result
        assert "revenue" in result
        assert "avg_price" in result
        assert "top_labels" in result
        assert isinstance(result["revenue"], Decimal)

    @pytest.mark.asyncio
    async def test_counts_non_negative(self, db_session):
        result = await get_summary(db_session, "30d")
        assert result["total_items"] >= 0
        assert result["sold"] >= 0
        assert result["in_stock"] >= 0


class TestDeadStock:
    @pytest.mark.asyncio
    async def test_dead_stock_structure(self, db_session):
        rows = await get_dead_stock(db_session, 0)
        for row in rows:
            assert "id" in row
            assert "barcode" in row
            assert "days_in_stock" in row
            assert row["days_in_stock"] >= 0

    @pytest.mark.asyncio
    async def test_sold_items_excluded(self, db_session):
        rows = await get_dead_stock(db_session, 0)
        for row in rows:
            assert "sold" not in str(row.get("status", ""))


class TestVelocity:
    @pytest.mark.asyncio
    async def test_velocity_structure(self, db_session):
        rows = await get_velocity(db_session)
        for row in rows:
            assert "category" in row
            assert "condition" in row
            assert "avg_days_to_sell" in row
            assert "sample_size" in row
            assert row["sample_size"] >= 2
