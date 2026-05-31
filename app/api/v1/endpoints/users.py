"""
app/api/v1/endpoints/users.py
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user, get_current_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import APIResponse
from app.schemas.user import (
    UserCreate, UserUpdate, UserResponse,
    LoginRequest, TokenResponse, RefreshRequest, APIKeyResponse,
)
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["Users"])


# ── Auth ──────────────────────────────────────────────────────────────────────

@router.post(
    "/register",
    response_model=APIResponse[UserResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register(payload: UserCreate, db: AsyncSession = Depends(get_db)):
    svc = UserService(db)
    user = await svc.create_user(payload)
    return APIResponse(data=UserResponse.model_validate(user), message="User registered successfully.")


@router.post(
    "/login",
    response_model=APIResponse[TokenResponse],
    summary="Login and receive JWT tokens",
)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    svc = UserService(db)
    tokens = await svc.login(payload)
    return APIResponse(data=TokenResponse(**tokens), message="Login successful.")


@router.post(
    "/refresh",
    response_model=APIResponse[TokenResponse],
    summary="Refresh access token",
)
async def refresh_token(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    svc = UserService(db)
    tokens = await svc.refresh_tokens(payload.refresh_token)
    return APIResponse(data=TokenResponse(**tokens), message="Tokens refreshed.")


# ── Profile ───────────────────────────────────────────────────────────────────

@router.get(
    "/me",
    response_model=APIResponse[UserResponse],
    summary="Get current user profile",
)
async def get_me(current_user: User = Depends(get_current_user)):
    return APIResponse(data=UserResponse.model_validate(current_user))


@router.patch(
    "/me",
    response_model=APIResponse[UserResponse],
    summary="Update current user profile",
)
async def update_me(
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = UserService(db)
    user = await svc.update_user(current_user.id, payload)
    return APIResponse(data=UserResponse.model_validate(user), message="Profile updated.")


@router.get(
    "/me/balance",
    response_model=APIResponse[dict],
    summary="Get current user balance",
)
async def get_balance(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = UserService(db)
    balance = await svc.get_balance(current_user.id)
    return APIResponse(data=balance)


@router.post(
    "/me/api-key",
    response_model=APIResponse[APIKeyResponse],
    summary="Rotate API key — returns raw key once",
)
async def rotate_api_key(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc = UserService(db)
    raw_key = await svc.rotate_api_key(current_user.id)
    return APIResponse(
        data=APIKeyResponse(api_key=raw_key),
        message="API key rotated. Store this securely — it will not be shown again.",
    )


# ── Admin ─────────────────────────────────────────────────────────────────────

@router.get(
    "/{user_id}",
    response_model=APIResponse[UserResponse],
    summary="[Admin] Get any user by ID",
)
async def get_user(
    user_id: str,
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    svc = UserService(db)
    user = await svc.get_user(user_id)
    return APIResponse(data=UserResponse.model_validate(user))


@router.delete(
    "/{user_id}",
    response_model=APIResponse[None],
    status_code=status.HTTP_200_OK,
    summary="[Admin] Soft-delete a user",
)
async def delete_user(
    user_id: str,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    svc = UserService(db)
    await svc.delete_user(user_id, actor_id=admin.id)
    return APIResponse(message="User deactivated.")
