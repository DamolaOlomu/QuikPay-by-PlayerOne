"""
app/models/transaction.py
Append-only transaction ledger. Transactions are NEVER mutated after settlement.
Status transitions happen via TransactionEvent audit rows.
"""
from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import String, Numeric, Enum as SAEnum, Text, Index, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin, ULIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class TransactionType(str, Enum):
    FUND_WALLET = "fund_wallet"
    BUY_GOODS = "buy_goods"
    CARD_PAYMENT = "card_payment"
    BANK_TRANSFER = "bank_transfer"
    PAY_BILL = "pay_bill"
    SEND_MONEY = "send_money"
    BUY_AIRTIME = "buy_airtime"
    BUY_DATA = "buy_data"
    WITHDRAW = "withdraw"
    DEPOSIT = "deposit"
    REFUND = "refund"
    REVERSAL = "reversal"
    FEE = "fee"


class TransactionStatus(str, Enum):
    INITIATED = "initiated"
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REVERSED = "reversed"
    REFUNDED = "refunded"


class TransactionOrigin(str, Enum):
    CUSTOMER = "customer"
    BUSINESS = "business"
    MERCHANT = "merchant"
    AGENT = "agent"
    SYSTEM = "system"


class PaymentChannel(str, Enum):
    WALLET = "wallet"
    CARD = "card"
    BANK_TRANSFER = "bank_transfer"
    VIRTUAL_ACCOUNT = "virtual_account"
    USSD = "ussd"
    BANK_APP = "bank_app"
    QR_CODE = "qr_code"
    PAYMENT_LINK = "payment_link"
    NIP = "nip"
    ATM = "atm"
    AGENT = "agent"
    API = "api"


# Allowed status state machine
VALID_TRANSITIONS: dict[TransactionStatus, set[TransactionStatus]] = {
    TransactionStatus.INITIATED: {TransactionStatus.PENDING, TransactionStatus.CANCELLED},
    TransactionStatus.PENDING: {
        TransactionStatus.PROCESSING,
        TransactionStatus.SUCCESS,
        TransactionStatus.FAILED,
        TransactionStatus.CANCELLED,
    },
    TransactionStatus.PROCESSING: {TransactionStatus.SUCCESS, TransactionStatus.FAILED},
    TransactionStatus.SUCCESS: {TransactionStatus.REVERSED, TransactionStatus.REFUNDED},
    TransactionStatus.FAILED: set(),
    TransactionStatus.CANCELLED: set(),
    TransactionStatus.REVERSED: set(),
    TransactionStatus.REFUNDED: set(),
}


class Transaction(ULIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_transactions_idempotency_key"),
        Index("ix_transactions_user_id", "user_id"),
        Index("ix_transactions_reference", "reference"),
        Index("ix_transactions_status", "status"),
        Index("ix_transactions_type", "transaction_type"),
    )

    # Core financial fields use Numeric for precision (not float)
    amount: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=4), nullable=False)
    fee: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=4), default=Decimal("0"), nullable=False)
    balance_before: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=4), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(precision=18, scale=4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="NGN", nullable=False)

    # Classification
    transaction_type: Mapped[TransactionType] = mapped_column(
        SAEnum(TransactionType, name="transactiontype"), nullable=False
    )
    status: Mapped[TransactionStatus] = mapped_column(
        SAEnum(TransactionStatus, name="transactionstatus"),
        default=TransactionStatus.INITIATED,
        nullable=False,
    )
    origin: Mapped[TransactionOrigin] = mapped_column(
        SAEnum(TransactionOrigin, name="transactionorigin"), nullable=False
    )
    channel: Mapped[PaymentChannel] = mapped_column(
        SAEnum(PaymentChannel, name="paymentchannel"), nullable=False
    )

    # Identifiers
    reference: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True)
    external_reference: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Parties
    user_id: Mapped[str] = mapped_column(String(26), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    counterparty_id: Mapped[Optional[str]] = mapped_column(String(26), nullable=True)
    counterparty_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    counterparty_account: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Metadata
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON blob

    # Reversal link
    reversed_by_id: Mapped[Optional[str]] = mapped_column(String(26), ForeignKey("transactions.id"), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="transactions")
    events: Mapped[List["TransactionEvent"]] = relationship(
        back_populates="transaction", order_by="TransactionEvent.created_at"
    )

    def can_transition_to(self, new_status: TransactionStatus) -> bool:
        return new_status in VALID_TRANSITIONS.get(self.status, set())


class TransactionEvent(ULIDPrimaryKeyMixin, TimestampMixin, Base):
    """Immutable audit log of every status change on a transaction."""
    __tablename__ = "transaction_events"

    transaction_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[Optional[TransactionStatus]] = mapped_column(
        SAEnum(TransactionStatus, name="transactionstatus2"), nullable=True
    )
    to_status: Mapped[TransactionStatus] = mapped_column(
        SAEnum(TransactionStatus, name="transactionstatus3"), nullable=False
    )
    actor: Mapped[str] = mapped_column(String(64), nullable=False)  # user_id | "system"
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    transaction: Mapped["Transaction"] = relationship(back_populates="events")
