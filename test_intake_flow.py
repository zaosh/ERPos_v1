"""
Integration tests — full intake flow from image upload to barcode generation.
Requires running test database.
"""
import pytest
import io
from PIL import Image
from unittest.mock import patch, AsyncMock


def make_test_jpeg(color=(50, 50, 50)) -> bytes:
    """Create a minimal test JPEG in memory."""
    img = Image.new("RGB", (200, 200), color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


MOCK_CV_RESULT = {
    "color": "black",
    "type": "band",
    "confidence": 0.75,
    "needs_review": False,
    "raw_output": {"model": "test"},
}


class TestIntakeFlow:
    @pytest.mark.asyncio
    async def test_capture_requires_auth(self, client):
        """Unauthenticated capture should return 401."""
        response = await client.post(
            "/items/capture",
            files={"image": ("shirt.jpg", make_test_jpeg(), "image/jpeg")},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_capture_returns_cv_result(self, client, staff_headers):
        """Capture endpoint should return CV analysis."""
        with patch("routes.items.analyze_image", return_value=MOCK_CV_RESULT):
            with patch("routes.items.save_temp_image", return_value="temp_123"):
                response = await client.post(
                    "/items/capture",
                    headers=staff_headers,
                    files={"image": ("shirt.jpg", make_test_jpeg(), "image/jpeg")},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["cv_result"]["color"] == "black"
        assert data["cv_result"]["type"] == "band"
        assert "temp_image_id" in data

    @pytest.mark.asyncio
    async def test_capture_rejects_non_image(self, client, staff_headers):
        """Non-image file should be rejected."""
        response = await client.post(
            "/items/capture",
            headers=staff_headers,
            files={"image": ("data.txt", b"not an image", "text/plain")},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_item_full_flow(self, client, staff_headers):
        """Create item with all required fields."""
        with patch("routes.items.finalize_image", return_value=("/data/images/TEST001.jpg", "/data/images/TEST001_thumb.jpg")):
            with patch("routes.items.print_label", return_value=True):
                response = await client.post(
                    "/items/",
                    headers=staff_headers,
                    json={
                        "temp_image_id": "temp_123",
                        "category": "tshirt",
                        "color": "black",
                        "type": "graphic",
                        "label": "acdc",
                        "size": "L",
                        "condition": "good",
                        "price": 12.00,
                    },
                )

        assert response.status_code == 201
        data = response.json()
        assert "barcode" in data
        assert "item_id" in data
        assert data["color"] == "black"
        assert data["label"] == "acdc"

    @pytest.mark.asyncio
    async def test_create_item_missing_required_field(self, client, staff_headers):
        """Missing price should fail validation."""
        response = await client.post(
            "/items/",
            headers=staff_headers,
            json={
                "temp_image_id": "temp_123",
                "category": "tshirt",
                "color": "black",
                "type": "graphic",
                "condition": "good",
                # price missing
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_item_invalid_condition(self, client, staff_headers):
        """Invalid enum value should fail."""
        response = await client.post(
            "/items/",
            headers=staff_headers,
            json={
                "temp_image_id": "temp_123",
                "category": "tshirt",
                "color": "black",
                "type": "graphic",
                "condition": "destroyed",  # not a valid enum
                "price": 5.00,
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_item_by_id(self, client, staff_headers, test_item):
        """Retrieve item by ID."""
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
    async def test_barcode_is_unique(self, client, staff_headers):
        """Two items should never get the same barcode."""
        barcodes = set()
        for _ in range(5):
            with patch("routes.items.finalize_image", return_value=("/test.jpg", "/test_thumb.jpg")):
                with patch("routes.items.print_label", return_value=True):
                    response = await client.post(
                        "/items/",
                        headers=staff_headers,
                        json={
                            "temp_image_id": f"temp_{_}",
                            "category": "tshirt",
                            "color": "grey",
                            "type": "plain",
                            "condition": "good",
                            "price": 5.00,
                        },
                    )
            if response.status_code == 201:
                barcodes.add(response.json()["barcode"])

        # All barcodes should be unique
        assert len(barcodes) == len([b for b in barcodes])


class TestCheckoutFlow:
    @pytest.mark.asyncio
    async def test_checkout_marks_items_sold(self, client, staff_headers, test_item):
        """Completing a sale should update item status to sold."""
        response = await client.post(
            "/sales/",
            headers=staff_headers,
            json={
                "items": [{"barcode": test_item.barcode}],
                "payment_type": "cash",
            },
        )
        assert response.status_code == 201

        # Verify item is now sold
        item_response = await client.get(f"/items/{test_item.id}", headers=staff_headers)
        assert item_response.json()["status"] == "sold"

    @pytest.mark.asyncio
    async def test_cannot_sell_already_sold_item(self, client, staff_headers, test_item):
        """Selling an already-sold item should fail."""
        # First sale
        await client.post(
            "/sales/",
            headers=staff_headers,
            json={"items": [{"barcode": test_item.barcode}], "payment_type": "cash"},
        )

        # Second attempt
        response = await client.post(
            "/sales/",
            headers=staff_headers,
            json={"items": [{"barcode": test_item.barcode}], "payment_type": "cash"},
        )
        assert response.status_code == 409  # Conflict

    @pytest.mark.asyncio
    async def test_checkout_invalid_barcode(self, client, staff_headers):
        """Unknown barcode should fail."""
        response = await client.post(
            "/sales/",
            headers=staff_headers,
            json={"items": [{"barcode": "DOESNOTEXIST"}], "payment_type": "cash"},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_void_sale_requires_admin(self, client, staff_headers):
        """Staff should not be able to void a sale."""
        response = await client.post(
            "/sales/1/void",
            headers=staff_headers,
            json={"reason": "test"},
        )
        assert response.status_code == 403
