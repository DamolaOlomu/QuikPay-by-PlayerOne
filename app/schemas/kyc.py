"""
app/schemas/kyc.py
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.kyc import KYCTier, KYCStatus


class KYCCreate(BaseModel):
    bvn: Optional[str] = Field(default=None, min_length=11, max_length=11, pattern=r"^\d+$")
    nin: Optional[str] = Field(default=None, min_length=11, max_length=11, pattern=r"^\d+$")
    id_type: Optional[str] = None
    id_number: Optional[str] = None
    id_expiry: Optional[str] = None


class KYCUpdate(BaseModel):
    status: Optional[KYCStatus] = None
    tier: Optional[KYCTier] = None
    rejection_reason: Optional[str] = None


class KYCResponse(BaseModel):
    id: str
    user_id: str
    tier: KYCTier
    status: KYCStatus
    daily_limit: float
    monthly_limit: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
