from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.glyde import to_minor_units
from app.models.transaction import TransactionStatus
from app.models.user import User, UserStatus
from app.schemas.transaction import BankTransferRequest, WalletFundRequest
from app.services.transaction_service import TransactionService

pytestmark = pytest.mark.asyncio


class FakeGlydeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def initialise_collection(self, **kwargs):
        self.calls.append(("initialise_collection", kwargs))
        return {
            "status": "success",
            "data": {
                "reference": "glyde_collection_ref",
                "status": "pending",
                "url": "https://pay.useglyde.test/checkout",
            },
        }

    async def initiate_transfer(self, **kwargs):
        self.calls.append(("initiate_transfer", kwargs))
        return {
            "status": "success",
            "data": {
                "reference": "glyde_transfer_ref",
                "merchant_reference": kwargs["reference"],
                "amount": 250000,
                "status": "pending",
                "fee": 2500,
            },
        }


async def _fund_user(db: AsyncSession, user_id: str, amount: float = 100_000.0):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one()
    user.balance = amount
    user.status = UserStatus.ACTIVE
    await db.flush()


def test_to_minor_units_converts_ngn_to_kobo():
    assert to_minor_units(Decimal("25.50")) == 2550


async def test_glyde_card_collection_is_attached_to_wallet_funding(
    db: AsyncSession,
    registered_user: dict,
):
    fake_glyde = FakeGlydeClient()
    svc = TransactionService(db, glyde_client=fake_glyde)
    original_enabled = svc.settings.GLYDE_ENABLED
    svc.settings.GLYDE_ENABLED = True
    try:
        txn = await svc.fund_wallet(
            WalletFundRequest(amount=Decimal("1500.00"), source="card"),
            registered_user["id"],
            idempotency_key="glyde-card-fund-001",
        )
    finally:
        svc.settings.GLYDE_ENABLED = original_enabled

    assert fake_glyde.calls[0][0] == "initialise_collection"
    assert fake_glyde.calls[0][1]["reference"] == txn.reference
    assert txn.external_reference == "glyde_collection_ref"
    assert txn.status == TransactionStatus.PENDING
    assert "glyde_response" in txn.metadata_json


async def test_glyde_transfer_is_attached_to_bank_transfer(
    db: AsyncSession,
    registered_user: dict,
):
    await _fund_user(db, registered_user["id"])
    fake_glyde = FakeGlydeClient()
    svc = TransactionService(db, glyde_client=fake_glyde)
    original_enabled = svc.settings.GLYDE_ENABLED
    svc.settings.GLYDE_ENABLED = True
    try:
        txn = await svc.create_bank_transfer(
            BankTransferRequest(
                amount=Decimal("2500.00"),
                bank_code="044",
                account_number="0123456789",
                account_name="Jane Doe",
            ),
            registered_user["id"],
            idempotency_key="glyde-bank-transfer-001",
        )
    finally:
        svc.settings.GLYDE_ENABLED = original_enabled

    assert fake_glyde.calls[0][0] == "initiate_transfer"
    assert fake_glyde.calls[0][1]["reference"] == txn.reference
    assert fake_glyde.calls[0][1]["amount"] == Decimal("2500.00")
    assert txn.external_reference == "glyde_transfer_ref"
    assert txn.status == TransactionStatus.PENDING
