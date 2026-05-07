"""Integration tests for bulk item intake."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

import io
import pytest
from unittest.mock import patch, AsyncMock
from sqlalchemy import select
from models.item import Item


def _jpg_bytes() -> bytes:
    # Minimal JPEG magic bytes + enough content to pass validation
    return b"\xff\xd8\xff" + b"\x00" * 100


async def _capture(client, headers, fake_redis):
    """Upload a temp image and return temp_image_id."""
    with patch("routes.items.detect_color", new_callable=AsyncMock, return_value="red"), \
         patch("services.storage_service.LocalStorage.save_temp", new_callable=AsyncMock) as mock_save:
        mock_save.return_value = "bulk-test-temp-id"
        # Set up fakeredis with the temp image data
        import json
        await fake_redis.set(
            "temp_image:bulk-test-temp-id",
            json.dumps({"path": "/tmp/test.jpg", "uploaded_by": 1}),
            ex=600,
        )
        return "bulk-test-temp-id"


class TestBulkIntake:
    @pytest.mark.asyncio
    async def test_bulk_creates_n_items(self, client, staff_headers, staff_user, fake_redis, db_session):
        """quantity=5 creates exactly 5 items in the DB, all sharing bulk_group_id."""
        import json
        # Simulate a captured temp image in fakeredis
        temp_id = "test-bulk-temp-001"
        await fake_redis.set(
            f"temp_image:{temp_id}",
            json.dumps({"path": "/tmp/does-not-exist.jpg", "uploaded_by": staff_user.id}),
            ex=600,
        )

        with patch("routes.items.detect_color", new_callable=AsyncMock, return_value="blue"), \
             patch("services.storage_service.LocalStorage.claim", new_callable=AsyncMock) as mock_claim, \
             patch("services.storage_service.LocalStorage.duplicate", new_callable=AsyncMock) as mock_dup, \
             patch("services.printer_service.generate_zpl", return_value="^XA^XZ"), \
             patch("services.queue_service.enqueue", new_callable=AsyncMock, return_value=99):
            mock_claim.return_value = ("/data/images/2026/05/1.jpg", "/data/images/2026/05/1_thumb.jpg")
            mock_dup.return_value = ("/data/images/2026/05/X.jpg", "/data/images/2026/05/X_thumb.jpg")

            resp = await client.post("/items/", headers=staff_headers, json={
                "temp_image_id": temp_id,
                "category": "tshirt",
                "color": "blue",
                "type": "plain",
                "condition": "good",
                "price": "5.00",
                "quantity": 5,
            })

        assert resp.status_code == 201
        data = resp.json()
        assert data["total"] == 5
        assert len(data["items"]) == 5
        assert "bulk_group_id" in data
        assert len(data["print_job_ids"]) == 5

        # All items share the same bulk_group_id
        group_id = data["bulk_group_id"]
        barcodes = [i["barcode"] for i in data["items"]]
        assert len(set(barcodes)) == 5  # all unique

    @pytest.mark.asyncio
    async def test_bulk_sequences_are_1_to_n(self, client, staff_headers, staff_user, fake_redis, db_session):
        import json
        temp_id = "test-bulk-temp-002"
        await fake_redis.set(
            f"temp_image:{temp_id}",
            json.dumps({"path": "/tmp/does-not-exist.jpg", "uploaded_by": staff_user.id}),
            ex=600,
        )

        with patch("routes.items.detect_color", new_callable=AsyncMock, return_value="green"), \
             patch("services.storage_service.LocalStorage.claim", new_callable=AsyncMock) as mock_claim, \
             patch("services.storage_service.LocalStorage.duplicate", new_callable=AsyncMock) as mock_dup, \
             patch("services.printer_service.generate_zpl", return_value="^XA^XZ"), \
             patch("services.queue_service.enqueue", new_callable=AsyncMock, return_value=88):
            mock_claim.return_value = ("/data/images/2026/05/10.jpg", "/data/images/2026/05/10_thumb.jpg")
            mock_dup.return_value = ("/data/images/2026/05/11.jpg", "/data/images/2026/05/11_thumb.jpg")

            resp = await client.post("/items/", headers=staff_headers, json={
                "temp_image_id": temp_id,
                "category": "tshirt",
                "color": "green",
                "type": "plain",
                "condition": "good",
                "price": "8.00",
                "quantity": 3,
            })

        assert resp.status_code == 201
        group_id = resp.json()["bulk_group_id"]

        # Check DB
        from sqlalchemy.dialects.postgresql import UUID as PG_UUID
        import uuid
        result = await db_session.execute(
            select(Item).where(Item.bulk_group_id == uuid.UUID(group_id)).order_by(Item.bulk_sequence)
        )
        items = result.scalars().all()
        assert [i.bulk_sequence for i in items] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_get_bulk_group(self, client, staff_headers, staff_user, fake_redis, db_session):
        import json, uuid
        temp_id = "test-bulk-temp-003"
        await fake_redis.set(
            f"temp_image:{temp_id}",
            json.dumps({"path": "/tmp/does-not-exist.jpg", "uploaded_by": staff_user.id}),
            ex=600,
        )

        with patch("routes.items.detect_color", new_callable=AsyncMock, return_value="red"), \
             patch("services.storage_service.LocalStorage.claim", new_callable=AsyncMock) as mock_claim, \
             patch("services.storage_service.LocalStorage.duplicate", new_callable=AsyncMock) as mock_dup, \
             patch("services.printer_service.generate_zpl", return_value="^XA^XZ"), \
             patch("services.queue_service.enqueue", new_callable=AsyncMock, return_value=77):
            mock_claim.return_value = ("/data/images/2026/05/20.jpg", "/data/images/2026/05/20_thumb.jpg")
            mock_dup.return_value = ("/data/images/2026/05/21.jpg", "/data/images/2026/05/21_thumb.jpg")

            create_resp = await client.post("/items/", headers=staff_headers, json={
                "temp_image_id": temp_id,
                "category": "tshirt",
                "color": "red",
                "type": "plain",
                "condition": "good",
                "price": "4.00",
                "quantity": 2,
            })

        group_id = create_resp.json()["bulk_group_id"]
        get_resp = await client.get(f"/items/bulk/{group_id}", headers=staff_headers)
        assert get_resp.status_code == 200
        items = get_resp.json()
        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_quantity_1_returns_single_item_response(self, client, staff_headers, staff_user, fake_redis):
        import json
        temp_id = "test-single-temp-001"
        await fake_redis.set(
            f"temp_image:{temp_id}",
            json.dumps({"path": "/tmp/does-not-exist.jpg", "uploaded_by": staff_user.id}),
            ex=600,
        )

        with patch("routes.items.detect_color", new_callable=AsyncMock, return_value="black"), \
             patch("services.image_service.claim_temp_image", new_callable=AsyncMock) as mock_claim, \
             patch("services.printer_service.generate_zpl", return_value="^XA^XZ"), \
             patch("services.queue_service.enqueue", new_callable=AsyncMock, return_value=55):
            mock_claim.return_value = ("/data/images/2026/05/single.jpg", "/data/images/2026/05/single_thumb.jpg")

            resp = await client.post("/items/", headers=staff_headers, json={
                "temp_image_id": temp_id,
                "category": "tshirt",
                "color": "black",
                "type": "plain",
                "condition": "good",
                "price": "9.00",
                "quantity": 1,
            })

        assert resp.status_code == 201
        data = resp.json()
        # Single item: no bulk fields
        assert "bulk_group_id" not in data or data.get("bulk_group_id") is None
        assert "barcode" in data
