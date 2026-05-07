"""Integration tests for checkout flow."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

import pytest
from decimal import Decimal
from models import Item, ItemStatus, ItemCategory, ItemType, ItemCondition


async def _make_item(db_session, barcode: str, user_id: int, price: float = 10.00) -> Item:
    item = Item(
        barcode=barcode,
        category=ItemCategory.tshirt,
        color="black",
        type=ItemType.plain,
        condition=ItemCondition.good,
        price=Decimal(str(price)),
        status=ItemStatus.in_stock,
        created_by=user_id,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


class TestMultiItemCheckout:
    @pytest.mark.asyncio
    async def test_multi_item_sale(self, client, staff_headers, staff_user, db_session):
        item1 = await _make_item(db_session, "THR-20260429-10001", staff_user.id, 10.00)
        item2 = await _make_item(db_session, "THR-20260429-10002", staff_user.id, 15.00)

        response = await client.post(
            "/sales/",
            headers=staff_headers,
            json={
                "items": [{"barcode": item1.barcode}, {"barcode": item2.barcode}],
                "payment_type": "cash",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert Decimal(str(data["total_amount"])) == Decimal("25.00")
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_discount_applied(self, client, staff_headers, staff_user, db_session):
        item = await _make_item(db_session, "THR-20260429-10003", staff_user.id, 20.00)

        response = await client.post(
            "/sales/",
            headers=staff_headers,
            json={
                "items": [{"barcode": item.barcode}],
                "payment_type": "card",
                "discount": 5.00,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert Decimal(str(data["total_amount"])) == Decimal("15.00")
        assert Decimal(str(data["discount_amount"])) == Decimal("5.00")

    @pytest.mark.asyncio
    async def test_sale_ref_format(self, client, staff_headers, staff_user, db_session):
        item = await _make_item(db_session, "THR-20260429-10004", staff_user.id)
        response = await client.post(
            "/sales/",
            headers=staff_headers,
            json={"items": [{"barcode": item.barcode}], "payment_type": "cash"},
        )
        assert response.status_code == 201
        sale_ref = response.json()["sale_ref"]
        assert sale_ref.startswith("SALE-")


class TestVoidSale:
    @pytest.mark.asyncio
    async def test_void_reverts_item_status(self, client, admin_headers, staff_headers, staff_user, db_session):
        item = await _make_item(db_session, "THR-20260429-10005", staff_user.id)

        sale_resp = await client.post(
            "/sales/",
            headers=staff_headers,
            json={"items": [{"barcode": item.barcode}], "payment_type": "cash"},
        )
        sale_id = sale_resp.json()["id"]

        await client.post(
            f"/sales/{sale_id}/void",
            headers=admin_headers,
            json={"reason": "test void reason"},
        )

        item_resp = await client.get(f"/items/{item.id}", headers=staff_headers)
        assert item_resp.json()["status"] == "in_stock"

    @pytest.mark.asyncio
    async def test_cannot_void_twice(self, client, admin_headers, staff_headers, staff_user, db_session):
        item = await _make_item(db_session, "THR-20260429-10006", staff_user.id)

        sale_resp = await client.post(
            "/sales/",
            headers=staff_headers,
            json={"items": [{"barcode": item.barcode}], "payment_type": "cash"},
        )
        sale_id = sale_resp.json()["id"]

        await client.post(f"/sales/{sale_id}/void", headers=admin_headers, json={"reason": "first void"})
        response = await client.post(f"/sales/{sale_id}/void", headers=admin_headers, json={"reason": "second void"})
        assert response.status_code == 409


class TestSaleValidation:
    @pytest.mark.asyncio
    async def test_empty_items_rejected(self, client, staff_headers):
        response = await client.post(
            "/sales/",
            headers=staff_headers,
            json={"items": [], "payment_type": "cash"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_negative_discount_rejected(self, client, staff_headers, staff_user, db_session):
        item = await _make_item(db_session, "THR-20260429-10007", staff_user.id)
        response = await client.post(
            "/sales/",
            headers=staff_headers,
            json={"items": [{"barcode": item.barcode}], "payment_type": "cash", "discount": -5},
        )
        assert response.status_code == 422
