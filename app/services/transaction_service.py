"""
app/services/transaction_service.py
Core payment processing logic — state machine, idempotency, balance ledger.
"""
from __future__ import annotations

import json
import secrets
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import (
    TransactionNotFoundError,
    InsufficientFundsError,
    InvalidStateTransitionError,
    IdempotencyConflictError,
    UserNotFoundError,
)
from app.core.logging import get_logger
from app.models.transaction import (
    Transaction, TransactionEvent, TransactionStatus, TransactionOrigin,
    VALID_TRANSITIONS,
)
from app.models.user import User
from app.schemas.transaction import TransactionCreate, TransactionStatusUpdate

log = get_logger(__name__)

# Simple fee schedule — replace with your real logic
FEE_SCHEDULE: dict[str, Decimal] = {
    "send_money": Decimal("0.015"),   # 1.5%
    "withdraw": Decimal("0.01"),
    "buy_airtime": Decimal("0.005"),
    "buy_data": Decimal("0.005"),
    "pay_bill": Decimal("0.01"),
    "buy_goods": Decimal("0.01"),
    "deposit": Decimal("0"),
    "refund": Decimal("0"),
    "reversal": Decimal("0"),
    "fee": Decimal("0"),
}
MAX_FEE = Decimal("500")  # cap at ₦500


def _calculate_fee(transaction_type: str, amount: Decimal) -> Decimal:
    rate = FEE_SCHEDULE.get(transaction_type, Decimal("0"))
    return min(amount * rate, MAX_FEE).quantize(Decimal("0.0001"))


def _generate_reference() -> str:
    return f"P1P{secrets.token_hex(10).upper()}"


class TransactionService:

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _get_user(self, user_id: str) -> User:
        result = await self.db.execute(
            select(User).where(User.id == user_id, User.is_deleted == False)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise UserNotFoundError()
        return user

    async def _check_idempotency(self, key: str) -> Optional[Transaction]:
        """Return existing transaction if this key was already processed."""
        result = await self.db.execute(
            select(Transaction).where(Transaction.idempotency_key == key)
        )
        return result.scalar_one_or_none()

    # ── Create ────────────────────────────────────────────────────────────────

    async def create_transaction(
        self,
        payload: TransactionCreate,
        initiating_user_id: str,
    ) -> Transaction:
        # Idempotency check
        if payload.idempotency_key:
            existing = await self._check_idempotency(payload.idempotency_key)
            if existing:
                log.info("transaction.idempotency_hit", key=payload.idempotency_key)
                return existing

        user = await self._get_user(initiating_user_id)
        fee = _calculate_fee(payload.transaction_type.value, payload.amount)
        total_debit = payload.amount + fee

        # Balance check for debit operations
        debit_types = {"send_money", "buy_goods", "pay_bill", "buy_airtime", "buy_data", "withdraw", "fee"}
        if payload.transaction_type.value in debit_types:
            if Decimal(str(user.balance)) < total_debit:
                raise InsufficientFundsError(
                    f"Need {total_debit} {user.currency}, have {user.balance}."
                )

        balance_before = Decimal(str(user.balance))

        txn = Transaction(
            reference=_generate_reference(),
            idempotency_key=payload.idempotency_key,
            amount=payload.amount,
            fee=fee,
            currency=payload.currency.upper(),
            balance_before=balance_before,
            balance_after=balance_before,  # updated below
            transaction_type=payload.transaction_type,
            status=TransactionStatus.INITIATED,
            origin=TransactionOrigin.CUSTOMER,
            channel=payload.channel,
            description=payload.description,
            metadata_json=json.dumps(payload.metadata) if payload.metadata else None,
            user_id=initiating_user_id,
            counterparty_id=payload.counterparty_id,
            counterparty_name=payload.counterparty_name,
            counterparty_account=payload.counterparty_account,
        )
        self.db.add(txn)
        await self.db.flush()

        # Record initiation event
        self.db.add(TransactionEvent(
            transaction_id=txn.id,
            from_status=None,
            to_status=TransactionStatus.INITIATED,
            actor=initiating_user_id,
            note="Transaction initiated",
        ))

        log.info(
            "transaction.created",
            txn_id=txn.id,
            reference=txn.reference,
            amount=str(payload.amount),
            type=payload.transaction_type.value,
        )
        return txn

    # ── Read ──────────────────────────────────────────────────────────────────

    async def get_transaction(self, txn_id: str, user_id: str) -> Transaction:
        result = await self.db.execute(
            select(Transaction)
            .where(Transaction.id == txn_id, Transaction.user_id == user_id)
            .options(selectinload(Transaction.events))
        )
        txn = result.scalar_one_or_none()
        if not txn:
            raise TransactionNotFoundError()
        return txn

    async def list_transactions(
        self,
        user_id: str,
        page: int = 1,
        per_page: int = 20,
        status: Optional[TransactionStatus] = None,
    ) -> tuple[list[Transaction], int]:
        q = select(Transaction).where(Transaction.user_id == user_id)
        if status:
            q = q.where(Transaction.status == status)

        count_q = select(func.count()).select_from(q.subquery())
        total = (await self.db.execute(count_q)).scalar_one()

        q = (
            q.order_by(Transaction.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .options(selectinload(Transaction.events))
        )
        rows = (await self.db.execute(q)).scalars().all()
        return list(rows), total

    # ── Status Transition ─────────────────────────────────────────────────────

    async def update_status(
        self,
        txn_id: str,
        payload: TransactionStatusUpdate,
        actor_id: str,
    ) -> Transaction:
        result = await self.db.execute(
            select(Transaction)
            .where(Transaction.id == txn_id)
            .options(selectinload(Transaction.events))
        )
        txn = result.scalar_one_or_none()
        if not txn:
            raise TransactionNotFoundError()

        if not txn.can_transition_to(payload.status):
            raise InvalidStateTransitionError(
                f"Cannot move from {txn.status.value} → {payload.status.value}."
            )

        old_status = txn.status
        txn.status = payload.status

        if payload.external_reference:
            txn.external_reference = payload.external_reference

        # Settle balance on success
        if payload.status == TransactionStatus.SUCCESS:
            user = await self._get_user(txn.user_id)
            debit_types = {"send_money", "buy_goods", "pay_bill", "buy_airtime", "buy_data", "withdraw", "fee"}
            if txn.transaction_type.value in debit_types:
                user.balance = float(Decimal(str(user.balance)) - txn.amount - txn.fee)
            else:
                user.balance = float(Decimal(str(user.balance)) + txn.amount - txn.fee)

            txn.balance_after = Decimal(str(user.balance))

        self.db.add(TransactionEvent(
            transaction_id=txn.id,
            from_status=old_status,
            to_status=payload.status,
            actor=actor_id,
            note=payload.note,
        ))

        log.info(
            "transaction.status_updated",
            txn_id=txn_id,
            from_status=old_status.value,
            to_status=payload.status.value,
            actor=actor_id,
        )
        return txn
