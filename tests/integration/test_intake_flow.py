"""
Integration tests — full intake flow from image upload to job enqueueing.
Requires running test database.
"""
import pytest
import io
from PIL import Image
from unittest.mock import patch, AsyncMock


def make_test_jpeg(color=(50, 50, 50)) -> bytes:
    img = Image.new("RGB", (200, 200), color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


class TestIntakeFlow:
    @pytest.mark.asyncio
    async def test_capture_requires_auth(self, client):
        response = await client.post(
            "/items/capture",
            files={"image": ("shirt.jpg", make_test_jpeg(), "image/jpeg")},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_capture_returns_temp_id_and_color(self, client, staff_headers):
        """Capture now returns only temp_image_id + color (no type/confidence)."""
        with patch("routes.items.save_temp_image", new_callable=AsyncMock, return_value="temp_abc"):
            with patch("routes.items.detect_color", new_callable=AsyncMock, return_value="black"):
                response = await client.post(
                    "/items/capture",
                    headers=staff_headers,
                    files={"image": ("shirt.jpg", make_test_jpeg(), "image/jpeg")},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["temp_image_id"] == "temp_abc"
        assert data["color"] == "black"
        assert "cv_result" not in data
        assert "confidence" not in data

    @pytest.mark.asyncio
    async def test_capture_rejects_non_image(self, client, staff_headers):
        response = await client.post(
            "/items/capture",
            headers=staff_headers,
            files={"image": ("data.txt", b"not an image", "text/plain")},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_item_enqueues_jobs(self, client, staff_headers):
        """POST /items/ must create item and return cv_job_id and print_job_id."""
        with patch("routes.items._claim_temp_image", new_callable=AsyncMock,
                   return_value=("/data/images/test.jpg", "/data/images/test_thumb.jpg")):
            response = await client.post(
                "/items/",
                headers=staff_headers,
                json={
                    "temp_image_id": "temp_123",
                    "category": "tshirt",
                    "color": "black",
                    "label": "acdc",
                    "size": "L",
                    "condition": "good",
                    "price": 12.00,
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert "barcode" in data
        assert data["color"] == "black"
        assert data["label"] == "acdc"
        assert data["type"] == "unknown"   # worker fills this via cv_phase_a
        assert "cv_job_id" in data
        assert "print_job_id" in data
        if data["cv_job_id"] is not None:
            assert isinstance(data["cv_job_id"], int)
        assert isinstance(data["print_job_id"], int)

    @pytest.mark.asyncio
    async def test_create_item_type_defaults_to_unknown(self, client, staff_headers):
        with patch("routes.items._claim_temp_image", new_callable=AsyncMock,
                   return_value=("/data/images/x.jpg", "/data/images/x_thumb.jpg")):
            response = await client.post(
                "/items/",
                headers=staff_headers,
                json={
                    "temp_image_id": "temp_notype",
                    "category": "pants",
                    "color": "blue",
                    "condition": "fair",
                    "price": 6.00,
                },
            )
        assert response.status_code == 201
        assert response.json()["type"] == "unknown"

    @pytest.mark.asyncio
    async def test_create_item_missing_required_field(self, client, staff_headers):
        response = await client.post(
            "/items/",
            headers=staff_headers,
            json={
                "temp_image_id": "temp_123",
                "category": "tshirt",
                "color": "black",
                "condition": "good",
                # price missing
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_item_invalid_condition(self, client, staff_headers):
        response = await client.post(
            "/items/",
            headers=staff_headers,
            json={
                "temp_image_id": "temp_123",
                "category": "tshirt",
                "color": "black",
                "condition": "destroyed",  # not a valid enum
                "price": 5.00,
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_item_by_id(self, client, staff_headers, test_item):
        response = await client.get(f"/items/{test_item.id}", headers=staff_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["barcode"] == test_item.barcode
        assert data["color"] == test_item.color

    @pytest.mark.asyncio
    async def test_get_nonexistent_item_returns_404(self, client, staff_headers):
        response = await client.get("/items/999999", headers=staff_headers)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_patch_item_by_barcode(self, client, staff_headers, test_item):
        response = await client.patch(
            f"/items/{test_item.barcode}",
            headers=staff_headers,
            json={"status": "archived"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "archived"
        assert data["barcode"] == test_item.barcode

    @pytest.mark.asyncio
    async def test_patch_item_unknown_barcode_returns_404(self, client, staff_headers):
        response = await client.patch(
            "/items/THR-DOES-NOT-EXIST",
            headers=staff_headers,
            json={"status": "archived"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_jobs_route_requires_auth(self, client):
        response = await client.get("/jobs/1/status")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_jobs_summary_requires_admin(self, client, staff_headers):
        response = await client.get("/jobs/summary", headers=staff_headers)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_jobs_summary_returns_structure(self, client, admin_headers):
        response = await client.get("/jobs/summary", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "pending_count" in data
        assert "failed_count" in data
        assert "pending_by_type" in data

    @pytest.mark.asyncio
    async def test_barcode_is_unique(self, client, staff_headers):
        barcodes = set()
        for _ in range(5):
            with patch("routes.items._claim_temp_image", new_callable=AsyncMock,
                       return_value=("/test.jpg", "/test_thumb.jpg")):
                response = await client.post(
                    "/items/",
                    headers=staff_headers,
                    json={
                        "temp_image_id": f"temp_{_}",
                        "category": "tshirt",
                        "color": "grey",
                        "condition": "good",
                        "price": 5.00,
                    },
                )
            if response.status_code == 201:
                barcodes.add(response.json()["barcode"])

        assert len(barcodes) == len([b for b in barcodes])


class TestCheckoutFlow:
    @pytest.mark.asyncio
    async def test_checkout_marks_items_sold(self, client, staff_headers, test_item):
        response = await client.post(
            "/sales/",
            headers=staff_headers,
            json={"items": [{"barcode": test_item.barcode}], "payment_type": "cash"},
        )
        assert response.status_code == 201

        item_response = await client.get(f"/items/{test_item.id}", headers=staff_headers)
        assert item_response.json()["status"] == "sold"

    @pytest.mark.asyncio
    async def test_cannot_sell_already_sold_item(self, client, staff_headers, test_item):
        await client.post(
            "/sales/",
            headers=staff_headers,
            json={"items": [{"barcode": test_item.barcode}], "payment_type": "cash"},
        )
        response = await client.post(
            "/sales/",
            headers=staff_headers,
            json={"items": [{"barcode": test_item.barcode}], "payment_type": "cash"},
        )
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_checkout_invalid_barcode(self, client, staff_headers):
        response = await client.post(
            "/sales/",
            headers=staff_headers,
            json={"items": [{"barcode": "DOESNOTEXIST"}], "payment_type": "cash"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_void_sale_requires_admin(self, client, staff_headers):
        response = await client.post(
            "/sales/1/void",
            headers=staff_headers,
            json={"reason": "test"},
        )
        assert response.status_code == 403
