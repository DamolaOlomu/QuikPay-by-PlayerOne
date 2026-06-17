"""
app/core/security.py
JWT creation/validation, password hashing, and API-key generation.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import get_settings

settings = get_settings()


# ── Password ──────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ── JWT ───────────────────────────────────────────────────────────────────────

def _make_token(data: dict[str, Any], expires_delta: timedelta) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + expires_delta
    payload["iat"] = datetime.now(timezone.utc)
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    data = {"sub": subject, "type": "access", **(extra or {})}
    return _make_token(data, timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))


def create_refresh_token(subject: str) -> str:
    data = {"sub": subject, "type": "refresh"}
    return _make_token(data, timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS))


def decode_token(token: str) -> dict[str, Any]:
    """
    Decode and validate a JWT. Raises JWTError on any failure.
    Callers should catch JWTError and convert to HTTP 401.
    """
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


# ── API Keys ──────────────────────────────────────────────────────────────────

def generate_api_key(prefix: str = "p1p") -> str:
    """Return a prefixed, URL-safe random API key (48 hex chars + prefix)."""
    return f"{prefix}_{secrets.token_hex(24)}"


def generate_idempotency_key() -> str:
    return secrets.token_hex(16)


# ── Webhook Signatures ────────────────────────────────────────────────────────

def sign_webhook_payload(payload: bytes, secret: str | None = None) -> str:
    """HMAC-SHA256 signature for outgoing webhook payloads."""
    key = (secret or settings.WEBHOOK_SECRET).encode()
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def verify_webhook_signature(payload: bytes, signature: str, secret: str | None = None) -> bool:
    expected = sign_webhook_payload(payload, secret)
    return hmac.compare_digest(expected, signature)