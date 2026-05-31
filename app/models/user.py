"""
app/models/user.py
"""
from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import String, Enum as SAEnum, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin, SoftDeleteMixin, ULIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.kyc import KYC
    from app.models.transaction import Transaction


class UserRole(str, Enum):
    CUSTOMER = "customer"
    AGENT = "agent"
    MERCHANT = "merchant"
    BUSINESS = "business"
    ADMIN = "admin"


class UserStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    PENDING_VERIFICATION = "pending_verification"
    CLOSED = "closed"


class User(ULIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_phone_number", "phone_number", unique=True),
        Index("ix_users_email", "email", unique=True),
    )

    # Identity
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, unique=True)
    fullname: Mapped[str] = mapped_column(String(255), nullable=False)

    # Auth
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    pin_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Access control
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="userrole"), default=UserRole.CUSTOMER, nullable=False
    )
    status: Mapped[UserStatus] = mapped_column(
        SAEnum(UserStatus, name="userstatus"),
        default=UserStatus.PENDING_VERIFICATION,
        nullable=False,
    )

    # API key (hashed) — used for machine-to-machine auth
    api_key_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)

    # Financial
    balance: Mapped[float] = mapped_column(default=0.0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="NGN", nullable=False)

    # Idempotency store (last key seen per user, prevents double-submit)
    last_idempotency_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Relationships
    kyc: Mapped[Optional["KYC"]] = relationship(back_populates="user", uselist=False)
    transactions: Mapped[List["Transaction"]] = relationship(
        back_populates="user", order_by="Transaction.created_at.desc()"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} phone={self.phone_number} role={self.role}>"
