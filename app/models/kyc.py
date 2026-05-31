"""
app/models/kyc.py
"""
from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import String, Enum as SAEnum, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin, ULIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class KYCTier(str, Enum):
    TIER_0 = "tier_0"   # Phone only
    TIER_1 = "tier_1"   # BVN verified
    TIER_2 = "tier_2"   # ID document verified
    TIER_3 = "tier_3"   # Full verification (address, face match)


class KYCStatus(str, Enum):
    PENDING = "pending"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class KYC(ULIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "kyc"

    user_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    tier: Mapped[KYCTier] = mapped_column(
        SAEnum(KYCTier, name="kyctier"), default=KYCTier.TIER_0, nullable=False
    )
    status: Mapped[KYCStatus] = mapped_column(
        SAEnum(KYCStatus, name="kycstatus"), default=KYCStatus.PENDING, nullable=False
    )

    # Document fields
    bvn: Mapped[Optional[str]] = mapped_column(String(11), nullable=True)
    nin: Mapped[Optional[str]] = mapped_column(String(11), nullable=True)
    id_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    id_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    id_expiry: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Document storage references (S3 keys / CDN paths — never raw data)
    id_front_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    id_back_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    selfie_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewer_id: Mapped[Optional[str]] = mapped_column(String(26), nullable=True)

    # Daily & monthly limits based on tier
    daily_limit: Mapped[float] = mapped_column(default=50_000.0, nullable=False)
    monthly_limit: Mapped[float] = mapped_column(default=200_000.0, nullable=False)

    user: Mapped["User"] = relationship(back_populates="kyc")
