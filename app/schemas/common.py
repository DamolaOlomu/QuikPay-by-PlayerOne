"""
app/schemas/common.py
Standardised API response envelope — every endpoint returns the same shape.
"""
from __future__ import annotations

from typing import Any, Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """
    Unified success envelope.

    {
      "success": true,
      "data": { ... },
      "message": "User created.",
      "request_id": "01HXZ..."
    }
    """
    success: bool = True
    data: Optional[T] = None
    message: str = "OK"
    request_id: Optional[str] = None


class PaginatedResponse(BaseModel, Generic[T]):
    """Cursor-based pagination envelope."""
    success: bool = True
    data: List[T]
    total: int
    page: int
    per_page: int
    has_next: bool
    next_cursor: Optional[str] = None
    request_id: Optional[str] = None


class ErrorResponse(BaseModel):
    """
    Unified error envelope — never leaks internal tracebacks.

    {
      "success": false,
      "error_code": "insufficient_funds",
      "message": "Account has insufficient funds.",
      "detail": null,
      "request_id": "01HXZ..."
    }
    """
    success: bool = False
    error_code: str
    message: str
    detail: Optional[Any] = None
    request_id: Optional[str] = None


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=20, ge=1, le=100)
    cursor: Optional[str] = None
