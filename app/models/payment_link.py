"""
app/models/payment_link.py
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from sqlalchemy import String, Enum as SAEnum, Numeric, DateTime, Boolean, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin, ULIDPrimaryKeyMixin


class PaymentLinkStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    EXPIRED = "expired"
    FULLY_PAID = "fully_paid"


class PaymentLink(ULIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "payment_links"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_payment_links_slug"),
    )

    creator_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Amount — if None, customer sets the amount themselves
    amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="NGN", nullable=False)

    # Settings
    collect_phone: Mapped[bool] = mapped_column(Boolean, default=True)
    collect_name: Mapped[bool] = mapped_column(Boolean, default=True)
    one_time_use: Mapped[bool] = mapped_column(Boolean, default=False)

    status: Mapped[PaymentLinkStatus] = mapped_column(
        SAEnum(PaymentLinkStatus, name="paymentlinkstatus"),
        default=PaymentLinkStatus.ACTIVE,
        nullable=False,
    )

    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Counters
    times_paid: Mapped[int] = mapped_column(default=0, nullable=False)
    total_collected: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"), nullable=False)

    creator = relationship("User", foreign_keys=[creator_id])
