from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserStatus

pytestmark = pytest.mark.asyncio


async def _fund_user(db: AsyncSession, user_id: str, amount: float = 100_000.0):
    from sqlalchemy import select

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one()
    user.balance = amount
    user.status = UserStatus.ACTIVE
    await db.flush()


async def _register_user(client: AsyncClient, phone: str, email: str) -> dict:
    resp = await client.post("/api/v1/users/register", json={
        "phone_number": phone,
        "fullname": "Second User",
        "email": email,
        "password": "SecurePass123!",
        "currency": "NGN",
    })
    assert resp.status_code == 201
    return resp.json()["data"]


class TestWallets:

    async def test_registered_user_has_wallet_id(self, registered_user: dict):
        assert registered_user["wallet_id"].startswith("WLT")
        assert len(registered_user["wallet_id"]) <= 32

    async def test_get_my_wallet(self, client: AsyncClient, auth_headers: dict, registered_user: dict):
        resp = await client.get("/api/v1/wallets/me", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["user_id"] == registered_user["id"]
        assert data["wallet_id"] == registered_user["wallet_id"]
        assert data["currency"] == "NGN"

    async def test_fund_wallet_initiates_explicit_transaction(
        self, client: AsyncClient, auth_headers: dict
    ):
        resp = await client.post(
            "/api/v1/wallets/fund",
            headers={**auth_headers, "Idempotency-Key": "wallet-fund-001"},
            json={
                "amount": "2500.00",
                "currency": "NGN",
                "source": "bank_transfer",
                "external_reference": "BANK-REF-001",
            },
        )

        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["transaction_type"] == "fund_wallet"
        assert data["channel"] == "bank_transfer"
        assert data["status"] == "initiated"
        assert data["idempotency_key"] == "wallet-fund-001"

    async def test_send_money_to_wallet_settles_both_wallets(
        self,
        client: AsyncClient,
        auth_headers: dict,
        registered_user: dict,
        db: AsyncSession,
    ):
        recipient = await _register_user(client, "+2348012345679", "second@example.com")
        await _fund_user(db, registered_user["id"], amount=10_000.0)
        await _fund_user(db, recipient["id"], amount=500.0)

        resp = await client.post(
            "/api/v1/wallets/send",
            headers={**auth_headers, "Idempotency-Key": "wallet-send-001"},
            json={
                "recipient_wallet_id": recipient["wallet_id"],
                "amount": "1000.00",
                "currency": "NGN",
                "description": "Lunch",
            },
        )

        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["transaction_type"] == "send_money"
        assert data["channel"] == "wallet"
        assert data["status"] == "success"
        assert data["counterparty_id"] == recipient["wallet_id"]
        assert float(data["balance_after"]) == 8985.0

        refreshed = await client.get("/api/v1/wallets/me", headers=auth_headers)
        assert float(refreshed.json()["data"]["balance"]) == 8985.0

    async def test_bank_transfer_requires_sufficient_wallet_balance(
        self, client: AsyncClient, auth_headers: dict
    ):
        resp = await client.post(
            "/api/v1/wallets/bank-transfers",
            headers=auth_headers,
            json={
                "amount": "50000.00",
                "currency": "NGN",
                "bank_code": "044",
                "account_number": "0123456789",
                "account_name": "Jane Doe",
            },
        )

        assert resp.status_code == 422
        assert resp.json()["error_code"] == "insufficient_funds"

    async def test_generate_virtual_account(self, client: AsyncClient, auth_headers: dict, registered_user: dict):
        resp = await client.post(
            "/api/v1/wallets/virtual-accounts",
            headers=auth_headers,
            json={"preferred_bank_code": "999001"},
        )

        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["wallet_id"] == registered_user["wallet_id"]
        assert len(data["account_number"]) == 10
        assert data["bank_code"] == "999001"
