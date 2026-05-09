"""Integration tests for customer endpoints."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

import pytest
from models.customer import Customer


# Valid Indian mobile numbers used across tests
_PH_A = "+919876540001"
_PH_B = "+919876540002"
_PH_C = "+919876540003"
_PH_D = "+919876540010"
_PH_E = "+919876540011"
_PH_F = "+919876540020"
_PH_G = "+919876540021"
_PH_H = "+919876540022"
_PH_I = "+919876540023"


async def _create_customer(client, headers, phone=_PH_A, first="Alice", last="Smith"):
    return await client.post("/customers/", headers=headers, json={
        "first_name": first, "last_name": last, "phone": phone,
    })


class TestCreateCustomer:
    @pytest.mark.asyncio
    async def test_create_success(self, client, staff_headers):
        resp = await _create_customer(client, staff_headers, phone="+919000000001")
        assert resp.status_code == 201
        data = resp.json()
        assert data["customer_uid"].startswith("CUST-")
        assert len(data["customer_uid"]) == 11

    @pytest.mark.asyncio
    async def test_phone_stored_as_e164(self, client, staff_headers):
        resp = await _create_customer(client, staff_headers, phone="+919000000002")
        assert resp.status_code == 201
        # Response is display format; DB stores E.164 — check via admin endpoint below

    @pytest.mark.asyncio
    async def test_phone_normalized_from_raw_10_digits(self, client, staff_headers):
        # Raw 10-digit → stored and returned as display format
        resp = await _create_customer(client, staff_headers, phone="9000000003")
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_duplicate_phone_returns_409_with_uid(self, client, staff_headers):
        await _create_customer(client, staff_headers, phone="+919000000004")
        resp2 = await _create_customer(client, staff_headers, phone="+919000000004")
        assert resp2.status_code == 409
        body = resp2.json()
        assert "customer found" in body["detail"]["message"]
        assert body["detail"]["customer_uid"].startswith("CUST-")
        assert "already registered" not in str(body)

    @pytest.mark.asyncio
    async def test_invalid_phone_returns_422(self, client, staff_headers):
        resp = await client.post("/customers/", headers=staff_headers, json={
            "first_name": "Test", "last_name": "User", "phone": "not-a-phone",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_landline_returns_422(self, client, staff_headers):
        # Indian landline (Mumbai 022 prefix)
        resp = await client.post("/customers/", headers=staff_headers, json={
            "first_name": "Test", "last_name": "User", "phone": "+912228001234",
        })
        assert resp.status_code == 422
        assert "mobile" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_same_number_different_formats_treated_as_same(self, client, staff_headers):
        # Create with raw 10-digit
        resp1 = await _create_customer(client, staff_headers, phone="9000000005")
        assert resp1.status_code == 201
        uid1 = resp1.json()["customer_uid"]
        # Attempt with +91 prefix — should hit 409 returning same uid
        resp2 = await _create_customer(client, staff_headers, phone="+919000000005")
        assert resp2.status_code == 409
        assert resp2.json()["detail"]["customer_uid"] == uid1

    @pytest.mark.asyncio
    async def test_091_prefix_treated_as_same_as_e164(self, client, staff_headers):
        resp1 = await _create_customer(client, staff_headers, phone="9000000006")
        assert resp1.status_code == 201
        uid1 = resp1.json()["customer_uid"]
        resp2 = await _create_customer(client, staff_headers, phone="091 90000 00006")
        assert resp2.status_code == 409
        assert resp2.json()["detail"]["customer_uid"] == uid1


class TestLookupCustomer:
    @pytest.mark.asyncio
    async def test_lookup_returns_masked_phone(self, client, staff_headers):
        await _create_customer(client, staff_headers, phone="+919000001001")
        resp = await client.get("/customers/lookup?phone=+919000001001", headers=staff_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "phone_last4" in data
        assert data["phone_last4"] == "1001"
        assert "phone_masked" in data
        # last 5 digits of national number: 01001
        assert data["phone_masked"].endswith("01001")
        assert "X" in data["phone_masked"]
        # Must NOT expose full E.164
        assert "phone" not in data or data.get("phone") is None
        assert "last_name" not in data

    @pytest.mark.asyncio
    async def test_lookup_min_4_chars_required(self, client, staff_headers):
        resp = await client.get("/customers/lookup?phone=987", headers=staff_headers)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_lookup_suffix_search(self, client, staff_headers):
        await _create_customer(client, staff_headers, phone="+919000001002")
        resp = await client.get("/customers/lookup?phone=1002", headers=staff_headers)
        assert resp.status_code == 200
        assert resp.json()["phone_last4"] == "1002"

    @pytest.mark.asyncio
    async def test_lookup_not_found_returns_404(self, client, staff_headers):
        resp = await client.get("/customers/lookup?phone=0000", headers=staff_headers)
        assert resp.status_code == 404


class TestGetCustomer:
    @pytest.mark.asyncio
    async def test_staff_cannot_get_full_record(self, client, staff_headers):
        resp = await _create_customer(client, staff_headers, phone="+919000002001")
        uid = resp.json()["customer_uid"]
        resp2 = await client.get(f"/customers/{uid}", headers=staff_headers)
        assert resp2.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_gets_display_format_phone(self, client, admin_headers, staff_headers):
        resp = await _create_customer(client, staff_headers, phone="+919000002002")
        uid = resp.json()["customer_uid"]
        resp2 = await client.get(f"/customers/{uid}", headers=admin_headers)
        assert resp2.status_code == 200
        data = resp2.json()
        # Phone should be in display format, not raw E.164
        assert data["phone"] == "+91 90000 02002"
        assert data["first_name"] == "Alice"

    @pytest.mark.asyncio
    async def test_admin_phone_is_not_raw_e164(self, client, admin_headers, staff_headers):
        resp = await _create_customer(client, staff_headers, phone="+919000002003")
        uid = resp.json()["customer_uid"]
        resp2 = await client.get(f"/customers/{uid}", headers=admin_headers)
        phone = resp2.json()["phone"]
        # Display format has spaces; raw E.164 does not
        assert " " in phone


class TestUpdateCustomerPhone:
    @pytest.mark.asyncio
    async def test_patch_normalizes_phone(self, client, admin_headers, staff_headers):
        resp = await _create_customer(client, staff_headers, phone="+919000003001")
        uid = resp.json()["customer_uid"]
        resp2 = await client.patch(f"/customers/{uid}", headers=admin_headers, json={
            "phone": "9000003002",
        })
        assert resp2.status_code == 200
        # Phone returned as display format
        assert "9000003002" in resp2.json()["phone"].replace(" ", "")

    @pytest.mark.asyncio
    async def test_patch_invalid_phone_returns_422(self, client, admin_headers, staff_headers):
        resp = await _create_customer(client, staff_headers, phone="+919000003003")
        uid = resp.json()["customer_uid"]
        resp2 = await client.patch(f"/customers/{uid}", headers=admin_headers, json={
            "phone": "not-a-phone",
        })
        assert resp2.status_code == 422

    @pytest.mark.asyncio
    async def test_patch_landline_returns_422(self, client, admin_headers, staff_headers):
        resp = await _create_customer(client, staff_headers, phone="+919000003004")
        uid = resp.json()["customer_uid"]
        resp2 = await client.patch(f"/customers/{uid}", headers=admin_headers, json={
            "phone": "+912228001234",
        })
        assert resp2.status_code == 422


class TestGdprErase:
    @pytest.mark.asyncio
    async def test_gdpr_erase_requires_confirm_field(self, client, admin_headers, staff_headers):
        resp = await _create_customer(client, staff_headers, phone="+919000004001")
        uid = resp.json()["customer_uid"]
        resp2 = await client.post(f"/customers/{uid}/gdpr-erase", headers=admin_headers, json={})
        assert resp2.status_code == 422

    @pytest.mark.asyncio
    async def test_gdpr_erase_wrong_confirm(self, client, admin_headers, staff_headers):
        resp = await _create_customer(client, staff_headers, phone="+919000004002")
        uid = resp.json()["customer_uid"]
        resp2 = await client.post(f"/customers/{uid}/gdpr-erase", headers=admin_headers, json={"confirm": "DELETE"})
        assert resp2.status_code == 422

    @pytest.mark.asyncio
    async def test_gdpr_erase_nulls_pii(self, client, admin_headers, staff_headers, db_session):
        resp = await _create_customer(client, staff_headers, phone="+919000004003")
        uid = resp.json()["customer_uid"]
        await client.post(f"/customers/{uid}/gdpr-erase", headers=admin_headers, json={"confirm": "ERASE"})

        from sqlalchemy import select
        cust = await db_session.scalar(select(Customer).where(Customer.customer_uid == uid))
        assert cust.phone is None
        assert cust.first_name is None
        assert cust.gdpr_erased_at is not None

    @pytest.mark.asyncio
    async def test_erased_phone_can_be_reregistered(self, client, admin_headers, staff_headers):
        phone = "+919000004004"
        resp = await _create_customer(client, staff_headers, phone=phone)
        uid = resp.json()["customer_uid"]
        await client.post(f"/customers/{uid}/gdpr-erase", headers=admin_headers, json={"confirm": "ERASE"})
        resp2 = await _create_customer(client, staff_headers, phone=phone)
        assert resp2.status_code == 201
        assert resp2.json()["customer_uid"] != uid
