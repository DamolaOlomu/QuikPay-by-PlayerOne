"""
app/api/v1/endpoints/wallets.py
Explicit wallet and money-movement endpoints.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user, get_idempotency_key
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.transaction import (
    AccountEnquiryResponse,
    BankTransferRequest,
    CardPaymentRequest,
    GlydeBalanceResponse,
    TransactionResponse,
    VirtualAccountRequest,
    VirtualAccountResponse,
    WalletFundRequest,
    WalletResponse,
    WalletSendRequest,
)
from app.services.transaction_service import TransactionService

router = APIRouter(prefix="/wallets", tags=["Wallets"])


@router.get(
    "/me",
    response_model=APIResponse[WalletResponse],
    summary="Get current user's wallet",
)
async def get_my_wallet(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    wallet = await TransactionService(db).get_wallet(current_user.id)
    return APIResponse(data=WalletResponse(**wallet))


@router.get(
    "/glyde/banks",
    response_model=APIResponse[dict],
    summary="List Glyde-supported banks",
)
async def list_glyde_banks(
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    banks = await TransactionService(db).list_banks()
    return APIResponse(data=banks)


@router.get(
    "/glyde/account-enquiry",
    response_model=APIResponse[AccountEnquiryResponse],
    summary="Verify a bank account through Glyde",
)
async def resolve_glyde_account_name(
    account_number: str = Query(min_length=10, max_length=10),
    bank_code: str = Query(min_length=2, max_length=10),
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    account = await TransactionService(db).resolve_account_name(account_number, bank_code)
    return APIResponse(data=AccountEnquiryResponse(**account))


@router.get(
    "/glyde/balance",
    response_model=APIResponse[GlydeBalanceResponse],
    summary="Check the configured Glyde wallet balance",
)
async def get_glyde_balance(
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    balance = await TransactionService(db).get_glyde_balance()
    return APIResponse(data=GlydeBalanceResponse(**balance))


@router.post(
    "/fund",
    response_model=APIResponse[TransactionResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Initiate wallet funding",
    description="Fund the user's wallet through card, bank transfer, or virtual account rails.",
)
async def fund_wallet(
    payload: WalletFundRequest,
    current_user: User = Depends(get_current_user),
    idempotency_key: Optional[str] = Depends(get_idempotency_key),
    db: AsyncSession = Depends(get_db),
):
    txn = await TransactionService(db).fund_wallet(payload, current_user.id, idempotency_key)
    return APIResponse(data=TransactionResponse.model_validate(txn), message="Wallet funding initiated.")


@router.post(
    "/send",
    response_model=APIResponse[TransactionResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Send money to another PlayerOnePay wallet",
)
async def send_to_wallet(
    payload: WalletSendRequest,
    current_user: User = Depends(get_current_user),
    idempotency_key: Optional[str] = Depends(get_idempotency_key),
    db: AsyncSession = Depends(get_db),
):
    txn = await TransactionService(db).send_to_wallet(payload, current_user.id, idempotency_key)
    return APIResponse(data=TransactionResponse.model_validate(txn), message="Wallet transfer completed.")


@router.post(
    "/card-payments",
    response_model=APIResponse[TransactionResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Initiate a card payment",
)
async def create_card_payment(
    payload: CardPaymentRequest,
    current_user: User = Depends(get_current_user),
    idempotency_key: Optional[str] = Depends(get_idempotency_key),
    db: AsyncSession = Depends(get_db),
):
    txn = await TransactionService(db).create_card_payment(payload, current_user.id, idempotency_key)
    return APIResponse(data=TransactionResponse.model_validate(txn), message="Card payment initiated.")


@router.post(
    "/bank-transfers",
    response_model=APIResponse[TransactionResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Initiate an outbound bank transfer",
)
async def create_bank_transfer(
    payload: BankTransferRequest,
    current_user: User = Depends(get_current_user),
    idempotency_key: Optional[str] = Depends(get_idempotency_key),
    db: AsyncSession = Depends(get_db),
):
    txn = await TransactionService(db).create_bank_transfer(payload, current_user.id, idempotency_key)
    return APIResponse(data=TransactionResponse.model_validate(txn), message="Bank transfer initiated.")


@router.post(
    "/virtual-accounts",
    response_model=APIResponse[VirtualAccountResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Generate a virtual account for wallet funding",
)
async def generate_virtual_account(
    payload: VirtualAccountRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    account = await TransactionService(db).generate_virtual_account(payload, current_user.id)
    return APIResponse(data=VirtualAccountResponse(**account), message="Virtual account generated.")
