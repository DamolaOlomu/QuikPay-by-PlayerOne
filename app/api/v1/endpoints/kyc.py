"""
app/api/v1/endpoints/kyc.py
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user, get_current_admin
from app.db.session import get_db
from app.models.kyc import KYC
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.kyc import KYCCreate, KYCUpdate, KYCResponse
from app.core.exceptions import ResourceNotFoundError, DuplicateResourceError

router = APIRouter(prefix="/kyc", tags=["KYC"])


@router.post(
    "",
    response_model=APIResponse[KYCResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Submit KYC documents for verification",
)
async def submit_kyc(
    payload: KYCCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    existing = (await db.execute(select(KYC).where(KYC.user_id == current_user.id))).scalar_one_or_none()
    if existing:
        raise DuplicateResourceError("KYC record already exists. Use PATCH to update.")

    kyc = KYC(user_id=current_user.id, **payload.model_dump(exclude_unset=True))
    db.add(kyc)
    await db.flush()
    return APIResponse(data=KYCResponse.model_validate(kyc), message="KYC submission received.", status_code=201)


@router.get(
    "/me",
    response_model=APIResponse[KYCResponse],
    summary="Get current user's KYC status",
)
async def get_my_kyc(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    kyc = (await db.execute(select(KYC).where(KYC.user_id == current_user.id))).scalar_one_or_none()
    if not kyc:
        raise ResourceNotFoundError("No KYC record found.")
    return APIResponse(data=KYCResponse.model_validate(kyc))


@router.patch(
    "/{kyc_id}",
    response_model=APIResponse[KYCResponse],
    summary="[Admin] Update KYC status / tier",
)
async def update_kyc(
    kyc_id: str,
    payload: KYCUpdate,
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    kyc = (await db.execute(select(KYC).where(KYC.id == kyc_id))).scalar_one_or_none()
    if not kyc:
        raise ResourceNotFoundError("KYC record not found.")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(kyc, field, value)

    # Adjust limits based on tier
    from app.models.kyc import KYCTier
    tier_limits = {
        KYCTier.TIER_0: (50_000, 200_000),
        KYCTier.TIER_1: (200_000, 1_000_000),
        KYCTier.TIER_2: (1_000_000, 5_000_000),
        KYCTier.TIER_3: (5_000_000, 20_000_000),
    }
    if payload.tier and payload.tier in tier_limits:
        kyc.daily_limit, kyc.monthly_limit = tier_limits[payload.tier]

    await db.flush()
    return APIResponse(data=KYCResponse.model_validate(kyc), message="KYC record updated.")
