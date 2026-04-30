"""
E2E smoke tests — full intake → checkout → analytics workflow.
Skipped unless THRIFT_E2E=1 env var is set (requires running Docker stack).
"""
import os
import sys
import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("THRIFT_E2E") != "1",
    reason="E2E tests require THRIFT_E2E=1 and running Docker stack",
)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))

BASE_URL = os.environ.get("THRIFT_E2E_URL", "http://localhost:8000")


@pytest.fixture
def api():
    import httpx
    with httpx.Client(base_url=BASE_URL, timeout=10) as client:
        yield client


def get_admin_token(api) -> str:
    resp = api.post("/auth/login", json={"username": "admin", "password": "changeme123"})
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


class TestFullWorkflow:
    def test_health_check(self, api):
        resp = api.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert resp.json()["db"] == "ok"

    def test_login_returns_token(self, api):
        token = get_admin_token(api)
        assert token
        assert len(token) > 10

    def test_analytics_dashboard_loads(self, api):
        token = get_admin_token(api)
        headers = {"Authorization": f"Bearer {token}"}
        resp = api.get("/analytics/summary?period=7d", headers=headers)
        assert resp.status_code == 200
