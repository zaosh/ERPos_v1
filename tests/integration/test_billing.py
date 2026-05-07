"""Integration tests for billing: customer-linked sales, receipts, receipt_number uniqueness."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

import asyncio
import pytest
from decimal import Decimal
from models import Item, ItemCategory, ItemType, ItemCondition, ItemStatus


async def _make_item(db_session, barcode: str, user_id: int, price: float = 10.00) -> Item:
    item = Item(
        barcode=barcode, category=ItemCategory.tshirt, color="red",
        type=ItemType.plain, condition=ItemCondition.good,
        price=Decimal(str(price)), status=ItemStatus.in_stock, created_by=user_id,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


async def _create_customer(client, headers, phone, idx=0):
    return await client.post("/customers/", headers=headers, json={
        "first_name": "Test", "last_name": "User", "phone": phone,
    })


class TestSaleWithCustomer:
    @pytest.mark.asyncio
    async def test_sale_links_customer_id(self, client, staff_headers, staff_user, db_session):
        item = await _make_item(db_session, "THR-20260507-20001", staff_user.id)
        cust_resp = await _create_customer(client, staff_headers, "+15552220001")
        assert cust_resp.status_code == 201
        uid = cust_resp.json()["customer_uid"]

        resp = await client.post("/sales/", headers=staff_headers, json={
            "items": [{"barcode": item.barcode}],
            "payment_type": "cash",
            "customer_uid": uid,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["customer_id"] is not None
        assert data["receipt_number"].startswith("RCP-")

    @pytest.mark.asyncio
    async def test_anonymous_sale_still_works(self, client, staff_headers, staff_user, db_session):
        item = await _make_item(db_session, "THR-20260507-20002", staff_user.id)
        resp = await client.post("/sales/", headers=staff_headers, json={
            "items": [{"barcode": item.barcode}],
            "payment_type": "cash",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["customer_id"] is None
        assert data["subtotal"] == "10.00"
        assert data["tax_amount"] == "0.00"
        assert data["receipt_number"].startswith("RCP-")

    @pytest.mark.asyncio
    async def test_sale_monetary_fields_present(self, client, staff_headers, staff_user, db_session):
        item = await _make_item(db_session, "THR-20260507-20003", staff_user.id, price=20.00)
        resp = await client.post("/sales/", headers=staff_headers, json={
            "items": [{"barcode": item.barcode}],
            "payment_type": "cash",
            "discount": 5.00,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "subtotal" in data
        assert "discount_amount" in data
        assert "tax_rate" in data
        assert "tax_amount" in data
        assert Decimal(data["subtotal"]) == Decimal("20.00")
        assert Decimal(data["discount_amount"]) == Decimal("5.00")
        # total = subtotal - discount + tax (tax=0 by default)
        assert Decimal(data["total_amount"]) == Decimal("15.00")

    @pytest.mark.asyncio
    async def test_invalid_customer_uid_returns_404(self, client, staff_headers, staff_user, db_session):
        item = await _make_item(db_session, "THR-20260507-20004", staff_user.id)
        resp = await client.post("/sales/", headers=staff_headers, json={
            "items": [{"barcode": item.barcode}],
            "payment_type": "cash",
            "customer_uid": "CUST-ZZZZZZ",
        })
        assert resp.status_code == 404


class TestReceipt:
    @pytest.mark.asyncio
    async def test_get_receipt_returns_required_fields(self, client, staff_headers, staff_user, db_session):
        item = await _make_item(db_session, "THR-20260507-20010", staff_user.id, price=15.00)
        sale_resp = await client.post("/sales/", headers=staff_headers, json={
            "items": [{"barcode": item.barcode}], "payment_type": "cash",
        })
        sale_ref = sale_resp.json()["sale_ref"]

        resp = await client.get(f"/sales/{sale_ref}/receipt", headers=staff_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "store_name" in data
        assert "receipt_number" in data
        assert "line_items" in data
        assert "subtotal" in data
        assert "total_amount" in data
        assert "return_window_days" in data
        assert len(data["line_items"]) == 1


class TestReceiptNumberUniqueness:
    @pytest.mark.asyncio
    async def test_concurrent_sales_get_unique_receipt_numbers(
        self, client, staff_headers, staff_user, db_session
    ):
        """20 concurrent sales must each get a unique receipt_number."""
        N = 20
        items = []
        for i in range(N):
            item = await _make_item(db_session, f"THR-20260507-2100{i:02d}", staff_user.id)
            items.append(item)
        await db_session.commit()

        async def make_sale(item):
            return await client.post("/sales/", headers=staff_headers, json={
                "items": [{"barcode": item.barcode}], "payment_type": "cash",
            })

        responses = await asyncio.gather(*[make_sale(item) for item in items])
        assert all(r.status_code == 201 for r in responses), [r.json() for r in responses if r.status_code != 201]

        receipt_numbers = [r.json()["receipt_number"] for r in responses]
        assert len(set(receipt_numbers)) == N, f"Duplicate receipt numbers: {receipt_numbers}"
