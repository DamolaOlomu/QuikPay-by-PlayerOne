"""
app/core/exceptions.py
Domain exception hierarchy → clean HTTP responses via registered handlers.
"""
from __future__ import annotations

from typing import Any


class PlayerOnePayError(Exception):
    """Base class for all application errors."""
    status_code: int = 500
    error_code: str = "internal_error"
    message: str = "An unexpected error occurred."

    def __init__(self, message: str | None = None, detail: Any = None):
        self.message = message or self.__class__.message
        self.detail = detail
        super().__init__(self.message)


# ── 400 Bad Request ───────────────────────────────────────────────────────────

class ValidationError(PlayerOnePayError):
    status_code = 422
    error_code = "validation_error"
    message = "Request validation failed."


class DuplicateResourceError(PlayerOnePayError):
    status_code = 409
    error_code = "duplicate_resource"
    message = "Resource already exists."


class InvalidStateTransitionError(PlayerOnePayError):
    status_code = 422
    error_code = "invalid_state_transition"
    message = "This state transition is not allowed."


class InsufficientFundsError(PlayerOnePayError):
    status_code = 422
    error_code = "insufficient_funds"
    message = "Account has insufficient funds for this transaction."


class IdempotencyConflictError(PlayerOnePayError):
    status_code = 409
    error_code = "idempotency_conflict"
    message = "A different request with the same idempotency key already exists."


# ── 401 / 403 ─────────────────────────────────────────────────────────────────

class AuthenticationError(PlayerOnePayError):
    status_code = 401
    error_code = "authentication_error"
    message = "Authentication required."


class AuthorizationError(PlayerOnePayError):
    status_code = 403
    error_code = "authorization_error"
    message = "You do not have permission to perform this action."


class InvalidTokenError(PlayerOnePayError):
    status_code = 401
    error_code = "invalid_token"
    message = "Token is invalid or expired."


# ── 404 ───────────────────────────────────────────────────────────────────────

class ResourceNotFoundError(PlayerOnePayError):
    status_code = 404
    error_code = "resource_not_found"
    message = "The requested resource was not found."


class UserNotFoundError(ResourceNotFoundError):
    error_code = "user_not_found"
    message = "User not found."


class TransactionNotFoundError(ResourceNotFoundError):
    error_code = "transaction_not_found"
    message = "Transaction not found."


# ── 429 ───────────────────────────────────────────────────────────────────────

class RateLimitExceededError(PlayerOnePayError):
    status_code = 429
    error_code = "rate_limit_exceeded"
    message = "Too many requests. Please slow down."


# ── 503 ───────────────────────────────────────────────────────────────────────

class ServiceUnavailableError(PlayerOnePayError):
    status_code = 503
    error_code = "service_unavailable"
    message = "An upstream service is temporarily unavailable."


class PaymentProcessorError(ServiceUnavailableError):
    error_code = "payment_processor_error"
    message = "Payment processor is unavailable. Please retry."
