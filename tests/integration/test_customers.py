"""Integration tests for customer endpoints."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

import asyncio
import pytest
from models.customer import Customer
from services.phone_service import normalize_phone


async def _create_customer(client, headers, phone="+15551110001", first="Alice", last="Smith"):
    return await client.post("/customers/", headers=headers, json={
        "first_name": first, "last_name": last, "phone": phone,
    })


class TestCreateCustomer:
    @pytest.mark.asyncio
    async def test_create_success(self, client, staff_headers):
        resp = await _create_customer(client, staff_headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["customer_uid"].startswith("CUST-")
        assert len(data["customer_uid"]) == 11
        assert data["phone"] == "+15551110001"

    @pytest.mark.asyncio
    async def test_duplicate_phone_returns_409_with_uid(self, client, staff_headers):
        await _create_customer(client, staff_headers, phone="+15551110002")
        resp2 = await _create_customer(client, staff_headers, phone="+15551110002")
        assert resp2.status_code == 409
        body = resp2.json()
        assert "customer found" in body["detail"]["message"]
        assert body["detail"]["customer_uid"].startswith("CUST-")
        # Must NOT say "already registered"
        assert "already registered" not in str(body)

    @pytest.mark.asyncio
    async def test_phone_normalized_to_e164(self, client, staff_headers):
        resp = await _create_customer(client, staff_headers, phone="(555) 333-4444")
        assert resp.status_code == 201
        assert resp.json()["phone"] == "+15553334444"


class TestLookupCustomer:
    @pytest.mark.asyncio
    async def test_lookup_returns_masked_only(self, client, staff_headers):
        await _create_customer(client, staff_headers, phone="+15551110003")
        resp = await client.get("/customers/lookup?phone=+15551110003", headers=staff_headers)
        assert resp.status_code == 200
        data = resp.json()
        # Must have masked fields
        assert "phone_last4" in data
        assert data["phone_last4"] == "0003"
        assert "last_initial" in data
        # Must NOT have full phone or full last name
        assert "phone" not in data or data.get("phone") is None
        assert "last_name" not in data

    @pytest.mark.asyncio
    async def test_lookup_min_4_chars_required(self, client, staff_headers):
        resp = await client.get("/customers/lookup?phone=555", headers=staff_headers)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_lookup_suffix_search(self, client, staff_headers):
        await _create_customer(client, staff_headers, phone="+15559876543")
        resp = await client.get("/customers/lookup?phone=6543", headers=staff_headers)
        assert resp.status_code == 200
        assert resp.json()["phone_last4"] == "6543"

    @pytest.mark.asyncio
    async def test_lookup_not_found_returns_404(self, client, staff_headers):
        resp = await client.get("/customers/lookup?phone=9999", headers=staff_headers)
        assert resp.status_code == 404


class TestGetCustomer:
    @pytest.mark.asyncio
    async def test_staff_cannot_get_full_record(self, client, staff_headers):
        resp = await _create_customer(client, staff_headers, phone="+15551110010")
        uid = resp.json()["customer_uid"]
        resp2 = await client.get(f"/customers/{uid}", headers=staff_headers)
        assert resp2.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_can_get_full_record(self, client, admin_headers, staff_headers):
        resp = await _create_customer(client, staff_headers, phone="+15551110011")
        uid = resp.json()["customer_uid"]
        resp2 = await client.get(f"/customers/{uid}", headers=admin_headers)
        assert resp2.status_code == 200
        data = resp2.json()
        assert data["phone"] == "+15551110011"
        assert data["first_name"] == "Alice"


class TestGdprErase:
    @pytest.mark.asyncio
    async def test_gdpr_erase_requires_confirm_field(self, client, admin_headers, staff_headers):
        resp = await _create_customer(client, staff_headers, phone="+15551110020")
        uid = resp.json()["customer_uid"]
        resp2 = await client.post(f"/customers/{uid}/gdpr-erase", headers=admin_headers, json={})
        assert resp2.status_code == 422

    @pytest.mark.asyncio
    async def test_gdpr_erase_wrong_confirm(self, client, admin_headers, staff_headers):
        resp = await _create_customer(client, staff_headers, phone="+15551110021")
        uid = resp.json()["customer_uid"]
        resp2 = await client.post(f"/customers/{uid}/gdpr-erase", headers=admin_headers, json={"confirm": "DELETE"})
        assert resp2.status_code == 422

    @pytest.mark.asyncio
    async def test_gdpr_erase_nulls_pii(self, client, admin_headers, staff_headers, db_session):
        resp = await _create_customer(client, staff_headers, phone="+15551110022")
        uid = resp.json()["customer_uid"]
        await client.post(f"/customers/{uid}/gdpr-erase", headers=admin_headers, json={"confirm": "ERASE"})

        from sqlalchemy import select
        from models.customer import Customer
        cust = await db_session.scalar(select(Customer).where(Customer.customer_uid == uid))
        assert cust.phone is None
        assert cust.first_name is None
        assert cust.gdpr_erased_at is not None

    @pytest.mark.asyncio
    async def test_erased_phone_can_be_reregistered(self, client, admin_headers, staff_headers):
        phone = "+15551110023"
        resp = await _create_customer(client, staff_headers, phone=phone)
        uid = resp.json()["customer_uid"]
        await client.post(f"/customers/{uid}/gdpr-erase", headers=admin_headers, json={"confirm": "ERASE"})
        # Re-register same phone number
        resp2 = await _create_customer(client, staff_headers, phone=phone)
        assert resp2.status_code == 201
        assert resp2.json()["customer_uid"] != uid  # New customer
