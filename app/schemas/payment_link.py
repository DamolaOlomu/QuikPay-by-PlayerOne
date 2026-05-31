"""
app/schemas/payment_link.py
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, AnyHttpUrl

from app.models.payment_link import PaymentLinkStatus


class PaymentLinkCreate(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    description: Optional[str] = Field(default=None, max_length=1000)
    amount: Optional[Decimal] = Field(default=None, gt=Decimal("0"))
    currency: str = Field(default="NGN", min_length=3, max_length=3)
    collect_phone: bool = True
    collect_name: bool = True
    one_time_use: bool = False
    expires_at: Optional[datetime] = None


class PaymentLinkUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=2, max_length=255)
    description: Optional[str] = None
    amount: Optional[Decimal] = Field(default=None, gt=Decimal("0"))
    status: Optional[PaymentLinkStatus] = None
    expires_at: Optional[datetime] = None


class PaymentLinkResponse(BaseModel):
    id: str
    slug: str
    url: str  # computed in service layer
    title: str
    description: Optional[str]
    amount: Optional[Decimal]
    currency: str
    status: PaymentLinkStatus
    collect_phone: bool
    collect_name: bool
    one_time_use: bool
    times_paid: int
    total_collected: Decimal
    expires_at: Optional[datetime]
    creator_id: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
