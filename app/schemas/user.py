"""
app/schemas/user.py
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, field_validator, model_validator, Field

from app.models.user import UserRole, UserStatus

PHONE_RE = re.compile(r"^\+?[1-9]\d{7,14}$")
PIN_RE = re.compile(r"^\d{4,6}$")


class UserCreate(BaseModel):
    phone_number: str
    fullname: str = Field(min_length=2, max_length=255)
    email: Optional[EmailStr] = None
    password: str = Field(min_length=8, max_length=128)
    pin: Optional[str] = None
    currency: str = Field(default="NGN", min_length=3, max_length=3)

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        cleaned = v.strip().replace(" ", "").replace("-", "")
        if not PHONE_RE.match(cleaned):
            raise ValueError("Invalid phone number format.")
        return cleaned

    @field_validator("pin")
    @classmethod
    def validate_pin(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not PIN_RE.match(v):
            raise ValueError("PIN must be 4–6 digits.")
        return v


class UserUpdate(BaseModel):
    fullname: Optional[str] = Field(default=None, min_length=2, max_length=255)
    email: Optional[EmailStr] = None


class UserPasswordUpdate(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class UserPINUpdate(BaseModel):
    current_pin: str
    new_pin: str = Field(min_length=4, max_length=6, pattern=r"^\d+$")


class UserResponse(BaseModel):
    id: str
    wallet_id: str
    phone_number: str
    fullname: str
    email: Optional[str]
    role: UserRole
    status: UserStatus
    balance: float
    currency: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserPublic(BaseModel):
    """Minimal public view — safe to return to counterparties."""
    id: str
    wallet_id: str
    fullname: str
    phone_number: str

    model_config = {"from_attributes": True}


# ── Auth Schemas ──────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    phone_number: str
    password: str

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return v.strip().replace(" ", "").replace("-", "")


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class RefreshRequest(BaseModel):
    refresh_token: str


class APIKeyResponse(BaseModel):
    api_key: str
    message: str = "Store this key securely. It will not be shown again."
