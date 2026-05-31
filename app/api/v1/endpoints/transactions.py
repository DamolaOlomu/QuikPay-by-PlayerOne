"""
app/api/v1/endpoints/transactions.py
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user, get_idempotency_key
from app.db.session import get_db
from app.models.transaction import TransactionStatus
from app.models.user import User
from app.schemas.common import APIResponse, PaginatedResponse
from app.schemas.transaction import (
    TransactionCreate, TransactionResponse, TransactionStatusUpdate,
)
from app.services.transaction_service import TransactionService

router = APIRouter(prefix="/transactions", tags=["Transactions"])


@router.post(
    "",
    response_model=APIResponse[TransactionResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Initiate a new transaction",
    description=(
        "Creates and initiates a transaction. Pass `Idempotency-Key` header "
        "to safely retry without duplicating the transaction."
    ),
)
async def create_transaction(
    payload: TransactionCreate,
    current_user: User = Depends(get_current_user),
    idempotency_key: Optional[str] = Depends(get_idempotency_key),
    db: AsyncSession = Depends(get_db),
):
    if idempotency_key:
        payload = payload.model_copy(update={"idempotency_key": idempotency_key})

    svc = TransactionService(db)
    txn = await svc.create_transaction(payload, initiating_user_id=current_user.id)
    return APIResponse(
        data=TransactionResponse.model_validate(txn),
        message="Transaction initiated.",
    )


@router.get(
    "",
    response_model=PaginatedResponse[TransactionResponse],
    summary="List current user's transactions",
)
async def list_transactions(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    status_filter: Optional[TransactionStatus] = Query(default=None, alias="status"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = TransactionService(db)
    txns, total = await svc.list_transactions(
        user_id=current_user.id,
        page=page,
        per_page=per_page,
        status=status_filter,
    )
    return PaginatedResponse(
        data=[TransactionResponse.model_validate(t) for t in txns],
        total=total,
        page=page,
        per_page=per_page,
        has_next=(page * per_page) < total,
    )


@router.get(
    "/{transaction_id}",
    response_model=APIResponse[TransactionResponse],
    summary="Get a single transaction (must belong to caller)",
)
async def get_transaction(
    transaction_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = TransactionService(db)
    txn = await svc.get_transaction(transaction_id, user_id=current_user.id)
    return APIResponse(data=TransactionResponse.model_validate(txn))


@router.patch(
    "/{transaction_id}/status",
    response_model=APIResponse[TransactionResponse],
    summary="Update transaction status (state machine enforced)",
    description=(
        "Advance the transaction through its lifecycle. "
        "Invalid transitions (e.g. FAILED → SUCCESS) are rejected with 422."
    ),
)
async def update_transaction_status(
    transaction_id: str,
    payload: TransactionStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = TransactionService(db)
    txn = await svc.update_status(transaction_id, payload, actor_id=current_user.id)
    return APIResponse(
        data=TransactionResponse.model_validate(txn),
        message=f"Transaction status updated to {txn.status.value}.",
    )
