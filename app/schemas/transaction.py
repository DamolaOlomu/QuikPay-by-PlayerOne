"""
app/schemas/transaction.py
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

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
