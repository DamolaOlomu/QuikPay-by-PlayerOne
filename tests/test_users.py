# tests/test_users.py
from __future__ import annotations

import pytest
from httpx import AsyncClient


pytestmark = pytest.mark.asyncio


class TestRegistration:

    async def test_register_success(self, client: AsyncClient):
        resp = await client.post("/api/v1/users/register", json={
            "phone_number": "+2348099999999",
            "fullname": "Jane Doe",
            "password": "Password123!",
            "currency": "NGN",
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["phone_number"] == "+2348099999999"
        assert "hashed_password" not in body["data"]

    async def test_register_duplicate_phone(self, client: AsyncClient, registered_user: dict):
        resp = await client.post("/api/v1/users/register", json={
            "phone_number": "+2348012345678",
            "fullname": "Duplicate",
            "password": "Password123!",
        })
        assert resp.status_code == 409
        assert resp.json()["error_code"] == "duplicate_resource"

    async def test_register_invalid_phone(self, client: AsyncClient):
        resp = await client.post("/api/v1/users/register", json={
            "phone_number": "not-a-phone",
            "fullname": "Bad Phone",
            "password": "Password123!",
        })
        assert resp.status_code == 422

    async def test_register_short_password(self, client: AsyncClient):
        resp = await client.post("/api/v1/users/register", json={
            "phone_number": "+2348011111111",
            "fullname": "Short",
            "password": "123",
        })
        assert resp.status_code == 422


class TestLogin:

    async def test_login_success(self, client: AsyncClient, registered_user: dict):
        resp = await client.post("/api/v1/users/login", json={
            "phone_number": "+2348012345678",
            "password": "SecurePass123!",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    async def test_login_wrong_password(self, client: AsyncClient, registered_user: dict):
        resp = await client.post("/api/v1/users/login", json={
            "phone_number": "+2348012345678",
            "password": "WrongPassword!",
        })
        assert resp.status_code == 401

    async def test_login_unknown_user(self, client: AsyncClient):
        resp = await client.post("/api/v1/users/login", json={
            "phone_number": "+2340000000000",
            "password": "AnyPassword!",
        })
        assert resp.status_code == 401


class TestProfile:

    async def test_get_me(self, client: AsyncClient, auth_headers: dict, registered_user: dict):
        resp = await client.get("/api/v1/users/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] == registered_user["id"]
        assert data["balance"] == 0.0

    async def test_get_me_unauthenticated(self, client: AsyncClient):
        resp = await client.get("/api/v1/users/me")
        assert resp.status_code == 401

    async def test_update_me(self, client: AsyncClient, auth_headers: dict):
        resp = await client.patch(
            "/api/v1/users/me",
            headers=auth_headers,
            json={"fullname": "Updated Name"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["fullname"] == "Updated Name"

    async def test_get_balance(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/users/me/balance", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "balance" in data
        assert "currency" in data


class TestRefreshToken:

    async def test_refresh_success(self, client: AsyncClient, registered_user: dict):
        login = await client.post("/api/v1/users/login", json={
            "phone_number": "+2348012345678",
            "password": "SecurePass123!",
        })
        refresh_token = login.json()["data"]["refresh_token"]

        resp = await client.post("/api/v1/users/refresh", json={"refresh_token": refresh_token})
        assert resp.status_code == 200
        assert "access_token" in resp.json()["data"]

    async def test_refresh_invalid_token(self, client: AsyncClient):
        resp = await client.post("/api/v1/users/refresh", json={"refresh_token": "bad.token.here"})
        assert resp.status_code == 401
