"""
app/api/v1/endpoints/payment_links.py
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user
from app.db.session import get_db
from app.models.payment_link import PaymentLink, PaymentLinkStatus
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.payment_link import PaymentLinkCreate, PaymentLinkUpdate, PaymentLinkResponse
from app.core.exceptions import ResourceNotFoundError, AuthorizationError
from app.core.config import get_settings

settings = get_settings()
router = APIRouter(prefix="/payment-links", tags=["Payment Links"])


def _build_url(slug: str) -> str:
    base = getattr(settings, "APP_BASE_URL", "https://pay.playeronepay.com")
    return f"{base}/pay/{slug}"


def _payment_link_response(link: PaymentLink) -> PaymentLinkResponse:
    return PaymentLinkResponse.model_validate({
        "id": link.id,
        "slug": link.slug,
        "url": _build_url(link.slug),
        "title": link.title,
        "description": link.description,
        "amount": link.amount,
        "currency": link.currency,
        "status": link.status,
        "collect_phone": link.collect_phone,
        "collect_name": link.collect_name,
        "one_time_use": link.one_time_use,
        "times_paid": link.times_paid,
        "total_collected": link.total_collected,
        "expires_at": link.expires_at,
        "creator_id": link.creator_id,
        "created_at": link.created_at,
        "updated_at": link.updated_at,
    })


@router.post(
    "",
    response_model=APIResponse[PaymentLinkResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a payment link",
)
async def create_payment_link(
    payload: PaymentLinkCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    slug = secrets.token_urlsafe(8)
    link = PaymentLink(
        creator_id=current_user.id,
        slug=slug,
        **payload.model_dump(exclude_unset=True),
    )
    db.add(link)
    await db.flush()

    return APIResponse(data=_payment_link_response(link), message="Payment link created.")


@router.get(
    "/{link_id}",
    response_model=APIResponse[PaymentLinkResponse],
    summary="Get a payment link",
)
async def get_payment_link(
    link_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    link = (await db.execute(select(PaymentLink).where(PaymentLink.id == link_id))).scalar_one_or_none()
    if not link:
        raise ResourceNotFoundError("Payment link not found.")

    return APIResponse(data=_payment_link_response(link))


@router.patch(
    "/{link_id}",
    response_model=APIResponse[PaymentLinkResponse],
    summary="Update a payment link",
)
async def update_payment_link(
    link_id: str,
    payload: PaymentLinkUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    link = (await db.execute(select(PaymentLink).where(PaymentLink.id == link_id))).scalar_one_or_none()
    if not link:
        raise ResourceNotFoundError()
    if link.creator_id != current_user.id:
        raise AuthorizationError("You do not own this payment link.")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(link, field, value)

    # Auto-expire
    if link.expires_at and link.expires_at < datetime.now(timezone.utc):
        link.status = PaymentLinkStatus.EXPIRED

    await db.flush()
    return APIResponse(data=_payment_link_response(link), message="Payment link updated.")


@router.delete(
    "/{link_id}",
    response_model=APIResponse[None],
    summary="Deactivate a payment link",
)
async def deactivate_payment_link(
    link_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    link = (await db.execute(select(PaymentLink).where(PaymentLink.id == link_id))).scalar_one_or_none()
    if not link:
        raise ResourceNotFoundError()
    if link.creator_id != current_user.id:
        raise AuthorizationError()
    link.status = PaymentLinkStatus.INACTIVE
    return APIResponse(message="Payment link deactivated.")
