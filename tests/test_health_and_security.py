# tests/test_health_and_security.py
from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


class TestHealth:

    async def test_health_returns_ok(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_response_has_request_id(self, client: AsyncClient):
        resp = await client.get("/health")
        assert "x-request-id" in resp.headers

    async def test_custom_request_id_echoed(self, client: AsyncClient):
        resp = await client.get("/health", headers={"X-Request-ID": "my-trace-id-123"})
        assert resp.headers.get("x-request-id") == "my-trace-id-123"

    async def test_response_time_header_present(self, client: AsyncClient):
        resp = await client.get("/health")
        assert "x-response-time-ms" in resp.headers


class TestSecurity:

    async def test_protected_endpoint_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/users/me")
        assert resp.status_code == 401
        assert resp.json()["error_code"] == "authentication_error" or resp.status_code == 401

    async def test_invalid_bearer_token(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": "Bearer this.is.not.valid"}
        )
        assert resp.status_code == 401

    async def test_error_response_never_leaks_traceback(self, client: AsyncClient):
        """500 errors must return our envelope, not raw Python tracebacks."""
        resp = await client.get("/api/v1/users/me")
        body = resp.json()
        assert "success" in body
        assert "traceback" not in str(body).lower()
        assert "sqlalchemy" not in str(body).lower()


class TestWebhook:

    async def test_webhook_rejected_without_signature(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/webhooks/payment-processor",
            json={"event": "transaction.success", "data": {}},
        )
        assert resp.status_code == 422  # missing header

    async def test_webhook_rejected_with_bad_signature(self, client: AsyncClient):
        payload = json.dumps({"event": "transaction.success", "data": {}}).encode()
        resp = await client.post(
            "/api/v1/webhooks/payment-processor",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": "bad_signature",
            },
        )
        assert resp.status_code == 401

    async def test_webhook_accepted_with_valid_signature(self, client: AsyncClient):
        from app.core.config import get_settings
        settings = get_settings()

        payload = json.dumps({"event": "transaction.unknown", "data": {}}).encode()
        sig = hmac.new(
            settings.WEBHOOK_SECRET.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()

        resp = await client.post(
            "/api/v1/webhooks/payment-processor",
            content=payload,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": sig,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "received"


class TestPaymentLinks:

    async def test_create_payment_link(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post(
            "/api/v1/payment-links",
            headers=auth_headers,
            json={
                "title": "Settle your tab",
                "description": "June dinner balance",
                "amount": "15000.00",
                "currency": "NGN",
            },
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert "slug" in data
        assert "url" in data
        assert data["status"] == "active"
        assert float(data["amount"]) == 15000.0

    async def test_deactivate_payment_link(self, client: AsyncClient, auth_headers: dict):
        create = await client.post(
            "/api/v1/payment-links",
            headers=auth_headers,
            json={"title": "To deactivate", "currency": "NGN"},
        )
        link_id = create.json()["data"]["id"]

        resp = await client.delete(f"/api/v1/payment-links/{link_id}", headers=auth_headers)
        assert resp.status_code == 200

    async def test_cannot_modify_other_users_link(self, client: AsyncClient, auth_headers: dict):
        create = await client.post(
            "/api/v1/payment-links",
            headers=auth_headers,
            json={"title": "Protected link", "currency": "NGN"},
        )
        link_id = create.json()["data"]["id"]

        # Second user
        await client.post("/api/v1/users/register", json={
            "phone_number": "+2348044445555",
            "fullname": "Other", "password": "Password123!",
        })
        login2 = await client.post("/api/v1/users/login", json={
            "phone_number": "+2348044445555", "password": "Password123!",
        })
        h2 = {"Authorization": f"Bearer {login2.json()['data']['access_token']}"}

        resp = await client.delete(f"/api/v1/payment-links/{link_id}", headers=h2)
        assert resp.status_code == 403
