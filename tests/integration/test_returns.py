"""Integration tests for returns flow."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

import pytest
from decimal import Decimal
from models import Item, ItemCategory, ItemType, ItemCondition, ItemStatus


async def _make_item(db_session, barcode, user_id, price=10.00, status=ItemStatus.in_stock):
    item = Item(
        barcode=barcode, category=ItemCategory.tshirt, color="blue",
        type=ItemType.plain, condition=ItemCondition.good,
        price=Decimal(str(price)), status=status, created_by=user_id,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)
    return item


async def _create_sale(client, headers, barcodes):
    resp = await client.post("/sales/", headers=headers, json={
        "items": [{"barcode": b} for b in barcodes], "payment_type": "cash",
    })
    assert resp.status_code == 201
    return resp.json()


class TestReturnBasic:
    @pytest.mark.asyncio
    async def test_return_within_window_succeeds(self, client, admin_headers, staff_headers, staff_user, db_session):
        item = await _make_item(db_session, "THR-20260507-30001", staff_user.id)
        sale = await _create_sale(client, staff_headers, [item.barcode])

        resp = await client.post("/returns/", headers=admin_headers, json={
            "sale_ref": sale["sale_ref"],
            "item_ids": [item.id],
            "return_reason": "Customer changed mind",
            "refund_method": "cash",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["return_ref"].startswith("RTN-")
        assert data["status"] == "completed"

    @pytest.mark.asyncio
    async def test_return_marks_item_in_stock_when_resellable(
        self, client, admin_headers, staff_headers, staff_user, db_session
    ):
        item = await _make_item(db_session, "THR-20260507-30002", staff_user.id)
        sale = await _create_sale(client, staff_headers, [item.barcode])

        await client.post("/returns/", headers=admin_headers, json={
            "sale_ref": sale["sale_ref"],
            "item_ids": [item.id],
            "return_reason": "Defect",
            "refund_method": "cash",
            "resellable": True,
        })

        item_resp = await client.get(f"/items/{item.id}", headers=staff_headers)
        assert item_resp.json()["status"] == "in_stock"

    @pytest.mark.asyncio
    async def test_return_marks_item_archived_when_not_resellable(
        self, client, admin_headers, staff_headers, staff_user, db_session
    ):
        item = await _make_item(db_session, "THR-20260507-30003", staff_user.id)
        sale = await _create_sale(client, staff_headers, [item.barcode])

        await client.post("/returns/", headers=admin_headers, json={
            "sale_ref": sale["sale_ref"],
            "item_ids": [item.id],
            "return_reason": "Damaged beyond repair",
            "refund_method": "cash",
            "resellable": False,
        })

        item_resp = await client.get(f"/items/{item.id}", headers=staff_headers)
        assert item_resp.json()["status"] == "archived"


class TestReturnValidation:
    @pytest.mark.asyncio
    async def test_item_not_in_sale_returns_400(
        self, client, admin_headers, staff_headers, staff_user, db_session
    ):
        item1 = await _make_item(db_session, "THR-20260507-30010", staff_user.id)
        item2 = await _make_item(db_session, "THR-20260507-30011", staff_user.id)
        sale = await _create_sale(client, staff_headers, [item1.barcode])

        resp = await client.post("/returns/", headers=admin_headers, json={
            "sale_ref": sale["sale_ref"],
            "item_ids": [item2.id],  # item2 was NOT in this sale
            "return_reason": "Wrong item",
            "refund_method": "cash",
        })
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_already_returned_item_returns_409(
        self, client, admin_headers, staff_headers, staff_user, db_session
    ):
        item = await _make_item(db_session, "THR-20260507-30012", staff_user.id)
        sale = await _create_sale(client, staff_headers, [item.barcode])

        await client.post("/returns/", headers=admin_headers, json={
            "sale_ref": sale["sale_ref"],
            "item_ids": [item.id],
            "return_reason": "First return",
            "refund_method": "cash",
        })

        resp2 = await client.post("/returns/", headers=admin_headers, json={
            "sale_ref": sale["sale_ref"],
            "item_ids": [item.id],
            "return_reason": "Second return attempt",
            "refund_method": "cash",
        })
        assert resp2.status_code == 409

    @pytest.mark.asyncio
    async def test_voided_sale_cannot_be_returned(
        self, client, admin_headers, staff_headers, staff_user, db_session
    ):
        item = await _make_item(db_session, "THR-20260507-30013", staff_user.id)
        sale = await _create_sale(client, staff_headers, [item.barcode])
        await client.post(f"/sales/{sale['id']}/void", headers=admin_headers, json={"reason": "test void"})

        resp = await client.post("/returns/", headers=admin_headers, json={
            "sale_ref": sale["sale_ref"],
            "item_ids": [item.id],
            "return_reason": "Return after void",
            "refund_method": "cash",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_staff_cannot_create_return(
        self, client, staff_headers, staff_user, db_session
    ):
        item = await _make_item(db_session, "THR-20260507-30014", staff_user.id)
        sale = await _create_sale(client, staff_headers, [item.barcode])

        resp = await client.post("/returns/", headers=staff_headers, json={
            "sale_ref": sale["sale_ref"],
            "item_ids": [item.id],
            "return_reason": "Staff attempting return",
            "refund_method": "cash",
        })
        assert resp.status_code == 403
