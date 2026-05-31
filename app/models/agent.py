"""
app/models/agent.py  &  app/models/atm.py  (combined for brevity)
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from sqlalchemy import String, Enum as SAEnum, Float, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base import TimestampMixin, SoftDeleteMixin, ULIDPrimaryKeyMixin


class AgentStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class Agent(ULIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "agents"

    user_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("users.id", ondelete="RESTRICT"), unique=True, nullable=False
    )
    kyc_id: Mapped[Optional[str]] = mapped_column(
        String(26), ForeignKey("kyc.id"), nullable=True
    )

    status: Mapped[AgentStatus] = mapped_column(
        SAEnum(AgentStatus, name="agentstatus"), default=AgentStatus.INACTIVE, nullable=False
    )

    # Location
    address: Mapped[str] = mapped_column(Text, nullable=False)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lga: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Financial limits
    float_balance: Mapped[float] = mapped_column(default=0.0, nullable=False)
    daily_transaction_limit: Mapped[float] = mapped_column(default=500_000.0, nullable=False)
    commission_rate: Mapped[float] = mapped_column(default=0.005, nullable=False)  # 0.5%

    user = relationship("User", foreign_keys=[user_id])
    kyc = relationship("KYC", foreign_keys=[kyc_id])
