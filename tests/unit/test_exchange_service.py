"""
Unit tests for exchange service.
Uses mocked DB sessions — tests pure service logic.
"""
import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

os.environ.setdefault("SECRET_KEY", "test_secret_key_that_is_at_least_64_characters_long_for_testing_only")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://thrift_user:thrift_pass@localhost:5432/thrift_store_test")
os.environ.setdefault("IMAGE_STORAGE_PATH", "/tmp/thrift_images_test")
os.environ.setdefault("IMAGE_BASE_URL", "http://localhost:8000/images")

from services.exchange_service import (
    ExchangeNotEligibleError,
    generate_exchange_ref,
    validate_exchange_eligibility,
)
from models.exchange import ExchangeStatus
from models.item import ItemStatus
from models.sale import Sale, SaleItem
from models.item import Item
from models.exchange import Exchange


def _make_sale(id=1, customer_id=10, created_at=None, voided_at=None):
    s = MagicMock(spec=Sale)
    s.id = id
    s.customer_id = customer_id
    s.created_at = created_at or datetime.now(timezone.utc) - timedelta(days=1)
    s.voided_at = voided_at
    return s


def _make_item(id=100, exchange_eligible=True, status=ItemStatus.sold):
    i = MagicMock(spec=Item)
    i.id = id
    i.exchange_eligible = exchange_eligible
    i.status = status
    i.exchange_fee_paid = Decimal("50")
    i.barcode = f"THR-{id}"
    return i


def _make_sale_item(sale_id=1, item_id=100):
    si = MagicMock(spec=SaleItem)
    si.sale_id = sale_id
    si.item_id = item_id
    si.price = Decimal("200")
    return si


class TestGenerateExchangeRef:
    @pytest.mark.asyncio
    async def test_format(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        db.scalar = AsyncMock(return_value=0)
        with patch("services.exchange_service._advisory_key", return_value=12345):
            ref = await generate_exchange_ref(db)
        assert ref.startswith("EXC-")
        parts = ref.split("-")
        assert len(parts) == 3
        assert len(parts[1]) == 8  # YYYYMMDD
        assert parts[2] == "0001"

    @pytest.mark.asyncio
    async def test_increments(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        db.scalar = AsyncMock(return_value=5)  # 5 existing today
        with patch("services.exchange_service._advisory_key", return_value=12345):
            ref = await generate_exchange_ref(db)
        assert ref.endswith("-0006")


class TestValidateExchangeEligibility:
    def _make_db_with(self, sale, sale_item, item, existing_exchange=None, window_days=30):
        db = AsyncMock()

        async def scalar_side_effect(query):
            # Return different objects based on which model is queried
            if hasattr(query, 'whereclause'):
                return None
            return None

        # We'll use a more targeted approach with sequential calls
        results = []

        # Call 1: sale lookup
        sale_result = AsyncMock()
        sale_result.scalar_one_or_none = MagicMock(return_value=sale)
        # Call 2: sale_item lookup
        si_result = AsyncMock()
        si_result.scalar_one_or_none = MagicMock(return_value=sale_item)
        # Call 3: item lookup
        item_result = AsyncMock()
        item_result.scalar_one_or_none = MagicMock(return_value=item)
        # Call 4: existing exchange lookup
        ex_result = AsyncMock()
        ex_result.scalar_one_or_none = MagicMock(return_value=existing_exchange)

        # Use scalar for direct scalar returns
        call_count = [0]
        scalar_returns = [sale, sale_item, item, existing_exchange]
        async def _scalar(*args, **kwargs):
            idx = call_count[0]
            call_count[0] += 1
            if idx < len(scalar_returns):
                return scalar_returns[idx]
            return None

        db.scalar = _scalar
        db.execute = AsyncMock()

        return db

    @pytest.mark.asyncio
    async def test_valid_case(self):
        sale = _make_sale(customer_id=10)
        sale_item = _make_sale_item(sale_id=1, item_id=100)
        item = _make_item(exchange_eligible=True, status=ItemStatus.sold)

        db = self._make_db_with(sale, sale_item, item, existing_exchange=None)

        with patch("services.exchange_service.settings_service.get_int", return_value=30):
            # Should not raise
            await validate_exchange_eligibility(100, 1, 10, db)

    @pytest.mark.asyncio
    async def test_fails_wrong_customer(self):
        sale = _make_sale(customer_id=99)  # Different customer
        sale_item = _make_sale_item()
        item = _make_item()

        db = self._make_db_with(sale, sale_item, item)

        with patch("services.exchange_service.settings_service.get_int", return_value=30):
            with pytest.raises(ExchangeNotEligibleError) as exc_info:
                await validate_exchange_eligibility(100, 1, 10, db)  # customer_id=10, sale has 99
        assert exc_info.value.code == "NOT_ON_SALE"

    @pytest.mark.asyncio
    async def test_fails_item_not_on_sale(self):
        sale = _make_sale(customer_id=10)
        # sale_item = None means item not on sale
        item = _make_item()

        call_count = [0]
        scalar_returns = [sale, None, item, None]  # None for sale_item
        async def _scalar(*args, **kwargs):
            idx = call_count[0]; call_count[0] += 1
            return scalar_returns[idx] if idx < len(scalar_returns) else None
        db = AsyncMock()
        db.scalar = _scalar
        db.execute = AsyncMock()

        with patch("services.exchange_service.settings_service.get_int", return_value=30):
            with pytest.raises(ExchangeNotEligibleError) as exc_info:
                await validate_exchange_eligibility(100, 1, 10, db)
        assert exc_info.value.code == "NOT_ON_SALE"

    @pytest.mark.asyncio
    async def test_fails_not_exchange_eligible(self):
        sale = _make_sale(customer_id=10)
        sale_item = _make_sale_item()
        item = _make_item(exchange_eligible=False, status=ItemStatus.sold)

        db = self._make_db_with(sale, sale_item, item)

        with patch("services.exchange_service.settings_service.get_int", return_value=30):
            with pytest.raises(ExchangeNotEligibleError) as exc_info:
                await validate_exchange_eligibility(100, 1, 10, db)
        assert exc_info.value.code == "NOT_ELIGIBLE"

    @pytest.mark.asyncio
    async def test_fails_already_exchanged_status(self):
        sale = _make_sale(customer_id=10)
        sale_item = _make_sale_item()
        item = _make_item(exchange_eligible=True, status=ItemStatus.exchanged)

        db = self._make_db_with(sale, sale_item, item)

        with patch("services.exchange_service.settings_service.get_int", return_value=30):
            with pytest.raises(ExchangeNotEligibleError) as exc_info:
                await validate_exchange_eligibility(100, 1, 10, db)
        assert exc_info.value.code == "ALREADY_EXCHANGED"

    @pytest.mark.asyncio
    async def test_fails_existing_exchange_row(self):
        sale = _make_sale(customer_id=10)
        sale_item = _make_sale_item()
        item = _make_item(exchange_eligible=True, status=ItemStatus.sold)
        existing_ex = MagicMock(spec=Exchange)
        existing_ex.exchange_ref = "EXC-20260509-0001"

        db = self._make_db_with(sale, sale_item, item, existing_exchange=existing_ex)

        with patch("services.exchange_service.settings_service.get_int", return_value=30):
            with pytest.raises(ExchangeNotEligibleError) as exc_info:
                await validate_exchange_eligibility(100, 1, 10, db)
        assert exc_info.value.code == "ALREADY_EXCHANGED"

    @pytest.mark.asyncio
    async def test_fails_window_expired(self):
        # Sale was 31 days ago, window is 30 days
        sale = _make_sale(
            customer_id=10,
            created_at=datetime.now(timezone.utc) - timedelta(days=31),
        )
        sale_item = _make_sale_item()
        item = _make_item(exchange_eligible=True, status=ItemStatus.sold)

        db = self._make_db_with(sale, sale_item, item, existing_exchange=None)

        with patch("services.exchange_service.settings_service.get_int", return_value=30):
            with pytest.raises(ExchangeNotEligibleError) as exc_info:
                await validate_exchange_eligibility(100, 1, 10, db)
        assert exc_info.value.code == "WINDOW_EXPIRED"
