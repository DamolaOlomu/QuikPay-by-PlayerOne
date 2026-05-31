"""
app/models/atm.py
"""
from __future__ import annotations

from enum import Enum
from typing import Optional
from decimal import Decimal

from sqlalchemy import String, Enum as SAEnum, Numeric, Text, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base import TimestampMixin, SoftDeleteMixin, ULIDPrimaryKeyMixin


class ATMStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"
    OUT_OF_CASH = "out_of_cash"


class ATM(ULIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "atms"

    terminal_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    bank_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    bank_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    status: Mapped[ATMStatus] = mapped_column(
        SAEnum(ATMStatus, name="atmstatus"), default=ATMStatus.OFFLINE, nullable=False
    )

    # Location
    address: Mapped[str] = mapped_column(Text, nullable=False)
    latitude: Mapped[Optional[float]] = mapped_column(nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Cash management
    cash_level: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    max_cash_capacity: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("5000000"), nullable=False)

    last_serviced_by: Mapped[Optional[str]] = mapped_column(String(26), nullable=True)
