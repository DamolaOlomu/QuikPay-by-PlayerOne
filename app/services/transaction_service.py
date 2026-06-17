"""
app/services/transaction_service.py
Core payment processing logic — state machine, idempotency, balance ledger.
"""
from __future__ import annotations

import json
import secrets
import hashlib
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value
from sqlalchemy.orm import selectinload

from app.core.exceptions import (
    TransactionNotFoundError,
    InsufficientFundsError,
    InvalidStateTransitionError,
    IdempotencyConflictError,
    UserNotFoundError,
)
from app.core.config import get_settings
from app.core.logging import get_logger
from app.integrations.glyde import GlydeClient
from app.models.base import _new_ulid, _now
from app.models.transaction import (
    Transaction, TransactionEvent, TransactionStatus, TransactionOrigin,
    TransactionType, PaymentChannel, VALID_TRANSITIONS,
)
from app.models.user import User
from app.schemas.transaction import (
    BankTransferRequest,
    CardPaymentRequest,
    TransactionCreate,
    TransactionStatusUpdate,
    VirtualAccountRequest,
    WalletFundRequest,
    WalletSendRequest,
)

log = get_logger(__name__)

# Simple fee schedule — replace with your real logic
FEE_SCHEDULE: dict[str, Decimal] = {
    "fund_wallet": Decimal("0"),
    "send_money": Decimal("0.015"),   # 1.5%
    "card_payment": Decimal("0.015"),
    "bank_transfer": Decimal("0.01"),
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

    def __init__(self, db: AsyncSession, glyde_client: Optional[GlydeClient] = None) -> None:
        self.db = db
        self.settings = get_settings()
        self.glyde = glyde_client or GlydeClient()

    async def _get_user(self, user_id: str) -> User:
        result = await self.db.execute(
            select(User).where(User.id == user_id, User.is_deleted == False)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise UserNotFoundError()
        return user

    async def _get_user_by_wallet_id(self, wallet_id: str) -> User:
        result = await self.db.execute(
            select(User).where(User.wallet_id == wallet_id, User.is_deleted == False)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise UserNotFoundError("Wallet not found.")
        return user

    async def _check_idempotency(self, key: str) -> Optional[Transaction]:
        """Return existing transaction if this key was already processed."""
        result = await self.db.execute(
            select(Transaction)
            .where(Transaction.idempotency_key == key)
            .options(selectinload(Transaction.events))
        )
        return result.scalar_one_or_none()

    def _metadata_json(self, metadata: Optional[dict]) -> Optional[str]:
        return json.dumps(metadata) if metadata else None

    def _read_metadata(self, txn: Transaction) -> dict[str, Any]:
        if not txn.metadata_json:
            return {}
        try:
            return json.loads(txn.metadata_json)
        except json.JSONDecodeError:
            return {}

    def _attach_provider_response(self, txn: Transaction, provider: str, response: dict[str, Any]) -> None:
        metadata = self._read_metadata(txn)
        metadata["provider"] = provider
        metadata[f"{provider}_response"] = response
        txn.metadata_json = json.dumps(metadata)

        data = response.get("data") or {}
        provider_reference = data.get("reference") or data.get("uid")
        if provider_reference:
            txn.external_reference = provider_reference
        if data.get("status") == "pending":
            txn.status = TransactionStatus.PENDING

    def _glyde_enabled(self) -> bool:
        return bool(self.settings.GLYDE_ENABLED)

    def _wallet_balance(self, user: User) -> Decimal:
        return Decimal(str(user.balance))

    def _build_transaction(
        self,
        *,
        user: User,
        amount: Decimal,
        currency: str,
        transaction_type: TransactionType,
        channel: PaymentChannel,
        status: TransactionStatus = TransactionStatus.INITIATED,
        fee: Optional[Decimal] = None,
        idempotency_key: Optional[str] = None,
        external_reference: Optional[str] = None,
        description: Optional[str] = None,
        metadata: Optional[dict] = None,
        counterparty_id: Optional[str] = None,
        counterparty_name: Optional[str] = None,
        counterparty_account: Optional[str] = None,
        balance_after: Optional[Decimal] = None,
    ) -> Transaction:
        balance_before = self._wallet_balance(user)
        computed_fee = fee if fee is not None else _calculate_fee(transaction_type.value, amount)
        txn = Transaction(
            reference=_generate_reference(),
            idempotency_key=idempotency_key,
            external_reference=external_reference,
            amount=amount,
            fee=computed_fee,
            currency=currency.upper(),
            balance_before=balance_before,
            balance_after=balance_after if balance_after is not None else balance_before,
            transaction_type=transaction_type,
            status=status,
            origin=TransactionOrigin.CUSTOMER,
            channel=channel,
            description=description,
            metadata_json=self._metadata_json(metadata),
            user_id=user.id,
            counterparty_id=counterparty_id,
            counterparty_name=counterparty_name,
            counterparty_account=counterparty_account,
        )
        self.db.add(txn)
        return txn

    def _add_event(
        self,
        txn: Transaction,
        actor_id: str,
        note: str,
        from_status: Optional[TransactionStatus] = None,
    ) -> None:
        now = _now()
        event = TransactionEvent(
            id=_new_ulid(),
            transaction_id=txn.id,
            from_status=from_status,
            to_status=txn.status,
            actor=actor_id,
            note=note,
            created_at=now,
            updated_at=now,
        )
        self.db.add(event)
        current_events = list(txn.__dict__.get("events", []))
        current_events.append(event)
        set_committed_value(txn, "events", current_events)

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
        debit_types = {"send_money", "bank_transfer", "buy_goods", "pay_bill", "buy_airtime", "buy_data", "withdraw", "fee"}
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
        self._add_event(txn, initiating_user_id, "Transaction initiated")

        log.info(
            "transaction.created",
            txn_id=txn.id,
            reference=txn.reference,
            amount=str(payload.amount),
            type=payload.transaction_type.value,
        )
        return txn

    async def get_wallet(self, user_id: str) -> dict:
        user = await self._get_user(user_id)
        return {
            "user_id": user.id,
            "wallet_id": user.wallet_id,
            "balance": self._wallet_balance(user),
            "currency": user.currency,
        }

    async def fund_wallet(
        self,
        payload: WalletFundRequest,
        user_id: str,
        idempotency_key: Optional[str] = None,
    ) -> Transaction:
        if idempotency_key:
            existing = await self._check_idempotency(idempotency_key)
            if existing:
                return existing

        user = await self._get_user(user_id)
        
        # Determine channel based on method and bank_transfer_option
        if payload.method == "card":
            channel = PaymentChannel.CARD
        elif payload.method == "bank_transfer":
            if payload.bank_transfer_option == "virtual_account":
                channel = PaymentChannel.VIRTUAL_ACCOUNT
            else:
                channel = PaymentChannel.BANK_TRANSFER
        else:
            channel = PaymentChannel.BANK_TRANSFER
        
        description = f"Fund wallet via {payload.method}"
        if payload.method == "bank_transfer":
            description += f" ({payload.bank_transfer_option})"
        
        txn = self._build_transaction(
            user=user,
            amount=payload.amount,
            currency=payload.currency,
            transaction_type=TransactionType.FUND_WALLET,
            channel=channel,
            idempotency_key=idempotency_key,
            external_reference=payload.external_reference,
            description=payload.description or description,
            metadata=payload.metadata,
        )
        await self.db.flush()
        
        if self._glyde_enabled():
            metadata = self._read_metadata(txn)
            metadata["bank_transfer_option"] = payload.bank_transfer_option
            txn.metadata_json = json.dumps(metadata)
            
            if payload.method == "card":
                response = await self.glyde.initialise_collection(
                    amount=payload.amount,
                    currency=payload.currency,
                    reference=txn.reference,
                    customer_name=user.fullname,
                    customer_email=user.email,
                    channels=["card_payment", "bank_transfer"],
                    default_channel="card_payment",
                )
                self._attach_provider_response(txn, "glyde", response)
            elif payload.method == "bank_transfer":
                if payload.bank_transfer_option == "virtual_account":
                    # Generate virtual account for user
                    va_response = await self.glyde.create_virtual_account({
                        "type": "dynamic",
                        "customer": {
                            "reference": user.wallet_id,
                            "first_name": user.fullname.split(maxsplit=1)[0],
                            "last_name": user.fullname.split(maxsplit=1)[1] if len(user.fullname.split(maxsplit=1)) > 1 else user.fullname.split(maxsplit=1)[0],
                            "email": user.email,
                            "phone": user.phone_number,
                        },
                        "expected_amount": int((payload.amount * Decimal("100")).quantize(Decimal("1"))),
                    })
                    self._attach_provider_response(txn, "glyde", va_response)
                else:
                    # Use Glyde's direct bank transfer
                    response = await self.glyde.collection_bank_transfer(
                        amount=payload.amount,
                        currency=payload.currency,
                        reference=txn.reference,
                        customer_name=user.fullname,
                        customer_email=user.email,
                    )
                    self._attach_provider_response(txn, "glyde", response)
        
        self._add_event(txn, user_id, "Wallet funding initiated")
        return txn

    async def send_to_wallet(
        self,
        payload: WalletSendRequest,
        sender_user_id: str,
        idempotency_key: Optional[str] = None,
    ) -> Transaction:
        if idempotency_key:
            existing = await self._check_idempotency(idempotency_key)
            if existing:
                return existing

        sender = await self._get_user(sender_user_id)
        recipient = await self._get_user_by_wallet_id(payload.recipient_wallet_id)
        if recipient.id == sender.id:
            raise IdempotencyConflictError("Cannot send money to the same wallet.")

        fee = _calculate_fee(TransactionType.SEND_MONEY.value, payload.amount)
        total_debit = payload.amount + fee
        sender_balance = self._wallet_balance(sender)
        if sender_balance < total_debit:
            raise InsufficientFundsError(f"Need {total_debit} {sender.currency}, have {sender.balance}.")

        recipient_balance = self._wallet_balance(recipient)
        sender_after = sender_balance - total_debit
        recipient_after = recipient_balance + payload.amount
        sender.balance = float(sender_after)
        recipient.balance = float(recipient_after)

        shared_reference = _generate_reference()
        sender_txn = self._build_transaction(
            user=sender,
            amount=payload.amount,
            currency=payload.currency,
            transaction_type=TransactionType.SEND_MONEY,
            channel=PaymentChannel.WALLET,
            status=TransactionStatus.SUCCESS,
            fee=fee,
            idempotency_key=idempotency_key,
            description=payload.description,
            metadata=payload.metadata,
            counterparty_id=recipient.wallet_id,
            counterparty_name=recipient.fullname,
            counterparty_account=recipient.wallet_id,
            balance_after=sender_after,
        )
        sender_txn.reference = shared_reference
        sender_txn.balance_before = sender_balance
        await self.db.flush()
        self._add_event(sender_txn, sender.id, "Wallet transfer completed")

        receiver_txn = self._build_transaction(
            user=recipient,
            amount=payload.amount,
            currency=payload.currency,
            transaction_type=TransactionType.FUND_WALLET,
            channel=PaymentChannel.WALLET,
            status=TransactionStatus.SUCCESS,
            fee=Decimal("0"),
            external_reference=shared_reference,
            description=payload.description or "Wallet transfer received",
            metadata=payload.metadata,
            counterparty_id=sender.wallet_id,
            counterparty_name=sender.fullname,
            counterparty_account=sender.wallet_id,
            balance_after=recipient_after,
        )
        receiver_txn.balance_before = recipient_balance
        await self.db.flush()
        self._add_event(receiver_txn, sender.id, "Wallet transfer received")
        return sender_txn

    async def create_card_payment(
        self,
        payload: CardPaymentRequest,
        user_id: str,
        idempotency_key: Optional[str] = None,
    ) -> Transaction:
        if idempotency_key:
            existing = await self._check_idempotency(idempotency_key)
            if existing:
                return existing

        user = await self._get_user(user_id)
        metadata = {
            **(payload.metadata or {}),
            "merchant_reference": payload.merchant_reference,
            "card_token": payload.card_token,
        }
        txn = self._build_transaction(
            user=user,
            amount=payload.amount,
            currency=payload.currency,
            transaction_type=TransactionType.CARD_PAYMENT,
            channel=PaymentChannel.CARD,
            idempotency_key=idempotency_key,
            external_reference=payload.merchant_reference,
            description=payload.description or "Card payment initiated",
            metadata=metadata,
        )
        await self.db.flush()
        if self._glyde_enabled():
            response = await self.glyde.initialise_collection(
                amount=payload.amount,
                currency=payload.currency,
                reference=txn.reference,
                customer_name=user.fullname,
                customer_email=user.email,
                channels=["card_payment"],
                default_channel="card_payment",
            )
            self._attach_provider_response(txn, "glyde", response)
        self._add_event(txn, user_id, "Card payment initiated")
        return txn

    async def create_bank_transfer(
        self,
        payload: BankTransferRequest,
        user_id: str,
        idempotency_key: Optional[str] = None,
    ) -> Transaction:
        if idempotency_key:
            existing = await self._check_idempotency(idempotency_key)
            if existing:
                return existing

        user = await self._get_user(user_id)
        fee = _calculate_fee(TransactionType.BANK_TRANSFER.value, payload.amount)
        total_debit = payload.amount + fee
        if self._wallet_balance(user) < total_debit:
            raise InsufficientFundsError(f"Need {total_debit} {user.currency}, have {user.balance}.")

        metadata = {
            **(payload.metadata or {}),
            "bank_code": payload.bank_code,
            "account_number": payload.account_number,
            "account_name": payload.account_name,
        }
        txn = self._build_transaction(
            user=user,
            amount=payload.amount,
            currency=payload.currency,
            transaction_type=TransactionType.BANK_TRANSFER,
            channel=PaymentChannel.BANK_TRANSFER,
            fee=fee,
            idempotency_key=idempotency_key,
            description=payload.narration or "Bank transfer initiated",
            metadata=metadata,
            counterparty_name=payload.account_name,
            counterparty_account=payload.account_number,
        )
        await self.db.flush()
        if self._glyde_enabled():
            response = await self.glyde.initiate_transfer(
                amount=payload.amount,
                bank_code=payload.bank_code,
                account_number=payload.account_number,
                reference=txn.reference,
            )
            self._attach_provider_response(txn, "glyde", response)
        self._add_event(txn, user_id, "Bank transfer initiated")
        return txn

    async def generate_virtual_account(
        self,
        payload: VirtualAccountRequest,
        user_id: str,
    ) -> dict:
        user = await self._get_user(user_id)
        if self._glyde_enabled():
            name_parts = user.fullname.split(maxsplit=1)
            customer = {
                "reference": user.wallet_id,
                "first_name": name_parts[0],
                "last_name": name_parts[1] if len(name_parts) > 1 else name_parts[0],
                "email": user.email,
                "phone": user.phone_number,
            }
            if payload.type == "static" and payload.bvn:
                customer["bvn"] = payload.bvn

            glyde_payload: dict[str, Any] = {
                "type": payload.type,
                "customer": customer,
            }
            if payload.expected_amount is not None:
                glyde_payload["expected_amount"] = int((payload.expected_amount * Decimal("100")).quantize(Decimal("1")))

            response = await self.glyde.create_virtual_account(glyde_payload)
            data = response.get("data") or {}
            return {
                "wallet_id": user.wallet_id,
                "provider_uid": data.get("uid"),
                "account_number": data.get("account_number", ""),
                "account_name": data.get("account_name", user.fullname),
                "bank_name": data.get("bank_name", ""),
                "bank_code": data.get("bank_code") or payload.preferred_bank_code,
                "currency": user.currency,
            }

        digest = hashlib.sha256(user.wallet_id.encode()).hexdigest()
        account_number = str(int(digest[:12], 16))[:10].ljust(10, "0")
        bank_code = payload.preferred_bank_code or "999001"
        return {
            "wallet_id": user.wallet_id,
            "provider_uid": None,
            "account_number": account_number,
            "account_name": user.fullname,
            "bank_name": "PlayerOnePay Virtual Bank",
            "bank_code": bank_code,
            "currency": user.currency,
        }

    async def list_banks(self) -> dict:
        return await self.glyde.banks()

    async def resolve_account_name(self, account_number: str, bank_code: str) -> dict:
        response = await self.glyde.account_enquiry(account_number=account_number, bank_code=bank_code)
        return response.get("data") or {}

    async def get_glyde_balance(self) -> dict:
        response = await self.glyde.balance()
        data = response.get("data") or {}
        if isinstance(data, list):
            data = data[0] if data else {}
        return data

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
            debit_types = {"send_money", "bank_transfer", "buy_goods", "pay_bill", "buy_airtime", "buy_data", "withdraw", "fee"}
            credit_types = {"deposit", "fund_wallet", "refund", "reversal"}
            if txn.transaction_type.value in debit_types:
                user.balance = float(Decimal(str(user.balance)) - txn.amount - txn.fee)
            elif txn.transaction_type.value in credit_types:
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
