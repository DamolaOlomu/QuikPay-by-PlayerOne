"""
app/services/user_service.py
All user business logic lives here — endpoints stay thin.
"""
from __future__ import annotations

import hashlib
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    DuplicateResourceError,
    AuthenticationError,
    UserNotFoundError,
    InvalidTokenError,
)
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_api_key,
)
from app.core.logging import get_logger
from app.models.user import User, UserStatus
from app.schemas.user import UserCreate, UserUpdate, LoginRequest

log = get_logger(__name__)


class UserService:

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _get_by_phone(self, phone: str) -> Optional[User]:
        result = await self.db.execute(
            select(User).where(User.phone_number == phone, User.is_deleted == False)
        )
        return result.scalar_one_or_none()

    async def _get_by_id(self, user_id: str) -> Optional[User]:
        result = await self.db.execute(
            select(User).where(User.id == user_id, User.is_deleted == False)
        )
        return result.scalar_one_or_none()

    # ── Create ────────────────────────────────────────────────────────────────

    async def create_user(self, payload: UserCreate) -> User:
        existing = await self._get_by_phone(payload.phone_number)
        if existing:
            raise DuplicateResourceError(
                f"A user with phone number {payload.phone_number} already exists."
            )

        user = User(
            phone_number=payload.phone_number,
            fullname=payload.fullname,
            email=payload.email,
            hashed_password=hash_password(payload.password),
            pin_hash=hash_password(payload.pin) if payload.pin else None,
            currency=payload.currency.upper(),
            status=UserStatus.PENDING_VERIFICATION,
        )
        self.db.add(user)
        await self.db.flush()  # get the generated ID without committing

        log.info("user.created", user_id=user.id, phone=user.phone_number)
        return user

    # ── Read ──────────────────────────────────────────────────────────────────

    async def get_user(self, user_id: str) -> User:
        user = await self._get_by_id(user_id)
        if not user:
            raise UserNotFoundError()
        return user

    # ── Update ────────────────────────────────────────────────────────────────

    async def update_user(self, user_id: str, payload: UserUpdate) -> User:
        user = await self.get_user(user_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(user, field, value)
        await self.db.flush()
        log.info("user.updated", user_id=user_id)
        return user

    # ── Soft-delete ───────────────────────────────────────────────────────────

    async def delete_user(self, user_id: str, actor_id: str) -> None:
        user = await self.get_user(user_id)
        user.soft_delete()
        log.warning("user.deleted", user_id=user_id, actor=actor_id)

    # ── Auth ──────────────────────────────────────────────────────────────────

    async def login(self, payload: LoginRequest) -> dict:
        user = await self._get_by_phone(payload.phone_number)
        if not user or not verify_password(payload.password, user.hashed_password):
            raise AuthenticationError("Invalid credentials.")
        if user.status == UserStatus.SUSPENDED:
            raise AuthenticationError("Account is suspended. Contact support.")

        access = create_access_token(subject=user.id, extra={"role": user.role})
        refresh = create_refresh_token(subject=user.id)

        log.info("user.login", user_id=user.id)
        return {
            "access_token": access,
            "refresh_token": refresh,
            "token_type": "bearer",
            "expires_in": 30 * 60,
        }

    async def refresh_tokens(self, refresh_token: str) -> dict:
        from jose import JWTError
        try:
            payload = decode_token(refresh_token)
            if payload.get("type") != "refresh":
                raise InvalidTokenError("Not a refresh token.")
            user_id = payload["sub"]
        except JWTError:
            raise InvalidTokenError()

        user = await self.get_user(user_id)
        access = create_access_token(subject=user.id, extra={"role": user.role})
        new_refresh = create_refresh_token(subject=user.id)

        return {
            "access_token": access,
            "refresh_token": new_refresh,
            "token_type": "bearer",
            "expires_in": 30 * 60,
        }

    # ── API Key ───────────────────────────────────────────────────────────────

    async def rotate_api_key(self, user_id: str) -> str:
        user = await self.get_user(user_id)
        raw_key = generate_api_key()
        # Store only the hash — raw key is shown once to the caller
        user.api_key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        await self.db.flush()
        log.warning("user.api_key_rotated", user_id=user_id)
        return raw_key

    # ── Balance ───────────────────────────────────────────────────────────────

    async def get_balance(self, user_id: str) -> dict:
        user = await self.get_user(user_id)
        return {"user_id": user.id, "balance": user.balance, "currency": user.currency}
