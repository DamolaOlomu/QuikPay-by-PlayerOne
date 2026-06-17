"""
app/schemas/transaction.py
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from app.models.transaction import TransactionType, TransactionStatus, TransactionOrigin, PaymentChannel


class TransactionCreate(BaseModel):
    amount: Decimal = Field(gt=Decimal("0"), description="Must be positive")
    currency: str = Field(default="NGN", min_length=3, max_length=3)
    transaction_type: TransactionType
    channel: PaymentChannel
    description: Optional[str] = Field(default=None, max_length=255)
    idempotency_key: Optional[str] = Field(default=None, max_length=64)

    # Counterparty
    counterparty_id: Optional[str] = None
    counterparty_name: Optional[str] = Field(default=None, max_length=255)
    counterparty_account: Optional[str] = Field(default=None, max_length=50)

    # Channel-specific metadata
    metadata: Optional[Dict[str, Any]] = None


class TransactionStatusUpdate(BaseModel):
    """Only the status field is updatable post-creation (state machine enforced)."""
    status: TransactionStatus
    note: Optional[str] = Field(default=None, max_length=512)
    external_reference: Optional[str] = Field(default=None, max_length=128)


class TransactionEventResponse(BaseModel):
    id: str
    from_status: Optional[TransactionStatus]
    to_status: TransactionStatus
    actor: str
    note: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class TransactionResponse(BaseModel):
    id: str
    reference: str
    idempotency_key: Optional[str]
    external_reference: Optional[str]

    amount: Decimal
    fee: Decimal
    currency: str
    balance_before: Decimal
    balance_after: Decimal

    transaction_type: TransactionType
    status: TransactionStatus
    origin: TransactionOrigin
    channel: PaymentChannel

    description: Optional[str]
    user_id: str
    counterparty_id: Optional[str]
    counterparty_name: Optional[str]
    counterparty_account: Optional[str]

    created_at: datetime
    updated_at: datetime

    events: List[TransactionEventResponse] = []

    model_config = {"from_attributes": True}


class TransactionListResponse(BaseModel):
    transactions: List[TransactionResponse]
    total: int
    has_next: bool


class WalletResponse(BaseModel):
    user_id: str
    wallet_id: str
    balance: Decimal
    currency: str


class WalletFundRequest(BaseModel):
    amount: Decimal = Field(gt=Decimal("0"))
    currency: str = Field(default="NGN", min_length=3, max_length=3)
    method: Literal["card", "bank_transfer"] = "bank_transfer"
    bank_transfer_option: Optional[Literal["glyde_bank_account", "virtual_account"]] = Field(
        default="glyde_bank_account",
        description="Only applicable when method is 'bank_transfer'. Choose 'glyde_bank_account' to use Glyde's supported banks or 'virtual_account' to generate a virtual account."
    )
    external_reference: Optional[str] = Field(default=None, max_length=128)
    description: Optional[str] = Field(default=None, max_length=255)
    metadata: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def validate_bank_transfer_option(self):
        if self.method == "card" and self.bank_transfer_option != "glyde_bank_account":
            # For card, bank_transfer_option should not matter, reset to default
            self.bank_transfer_option = "glyde_bank_account"
        elif self.method == "bank_transfer" and not self.bank_transfer_option:
            self.bank_transfer_option = "glyde_bank_account"
        return self


class WalletSendRequest(BaseModel):
    recipient_wallet_id: str = Field(min_length=6, max_length=32)
    amount: Decimal = Field(gt=Decimal("0"))
    currency: str = Field(default="NGN", min_length=3, max_length=3)
    description: Optional[str] = Field(default=None, max_length=255)
    metadata: Optional[Dict[str, Any]] = None


class CardPaymentRequest(BaseModel):
    amount: Decimal = Field(gt=Decimal("0"))
    currency: str = Field(default="NGN", min_length=3, max_length=3)
    merchant_reference: str = Field(min_length=1, max_length=128)
    card_token: str = Field(min_length=1, max_length=128)
    description: Optional[str] = Field(default=None, max_length=255)
    metadata: Optional[Dict[str, Any]] = None


class BankTransferRequest(BaseModel):
    amount: Decimal = Field(gt=Decimal("0"))
    currency: str = Field(default="NGN", min_length=3, max_length=3)
    bank_code: str = Field(min_length=2, max_length=10)
    account_number: str = Field(min_length=6, max_length=20)
    account_name: Optional[str] = Field(default=None, max_length=255)
    narration: Optional[str] = Field(default=None, max_length=255)
    metadata: Optional[Dict[str, Any]] = None


class VirtualAccountRequest(BaseModel):
    preferred_bank_code: Optional[str] = Field(default=None, min_length=2, max_length=10)
    type: Literal["dynamic", "static"] = "dynamic"
    expected_amount: Optional[Decimal] = Field(default=None, gt=Decimal("0"))
    bvn: Optional[str] = Field(default=None, min_length=11, max_length=11)


class VirtualAccountResponse(BaseModel):
    wallet_id: str
    provider_uid: Optional[str] = None
    account_number: str
    account_name: str
    bank_name: str
    bank_code: Optional[str] = None
    currency: str


class AccountEnquiryResponse(BaseModel):
    bank_name: Optional[str] = None
    account_name: str
    account_number: str


class GlydeBalanceResponse(BaseModel):
    balance: Decimal
    currency: str = "NGN"


class WalletFundResponse(BaseModel):
    wallet_id: str
    method: Literal["card", "bank_transfer"]
    bank_transfer_option: Optional[Literal["glyde_bank_account", "virtual_account"]] = None
    transaction: TransactionResponse
    funding_instructions: Optional[Dict[str, Any]] = None
